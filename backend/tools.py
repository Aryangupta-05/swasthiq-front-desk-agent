"""Six ground-truth tools. No model, network request, or caller instruction is executed here."""

import re
import sqlite3
from datetime import date
from pydantic import ValidationError
from . import models


class ToolError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def normalise(text):
    return " ".join(re.findall(r"\w+", text.lower(), flags=re.UNICODE))


def valid_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise ToolError("invalid_date", "Use a real calendar date in YYYY-MM-DD format") from None


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ToolError("invalid_time", "start must be HH:MM on a 15-minute boundary")
    h, m = map(int, value.split(":"))
    if m % 15:
        raise ToolError("invalid_time", "start must be HH:MM on a 15-minute boundary")
    return 60 * h + m


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


class Tools:
    schemas = {
        "lookup_patient": models.Lookup,
        "search_slots": models.Search,
        "book_appointment": models.Book,
        "reschedule_appointment": models.Move,
        "cancel_appointment": models.Cancel,
        "escalate_to_human": models.Escalate,
    }

    def __init__(self, schedule, today):
        self.schedule = schedule
        self.today = valid_date(today)
        self.calls = []
        self.events = []
        self.resolved = set()

    def call(self, tool_name, **arguments):
        if tool_name not in self.schemas:
            raise ToolError("unknown_tool", "Choose one of the six supported tools")
        # Record even rejected attempts, before validation or execution.
        self.calls.append({"name": tool_name, "arguments": arguments})
        try:
            args = self.schemas[tool_name].model_validate(arguments).model_dump()
            result = getattr(self, tool_name)(**args)
        except ValidationError as error:
            result = {
                "ok": False,
                "error": {
                    "code": "invalid_arguments",
                    "message": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()),
                },
            }
        except ToolError as error:
            result = {"ok": False, "error": {"code": error.code, "message": str(error)}}
        except sqlite3.IntegrityError as error:
            result = {"ok": False, "error": {"code": "slot_conflict", "message": str(error)}}
        self.events.append({"type": "tool", "name": tool_name, "arguments": arguments, "result": result})
        return result

    def lookup_patient(self, name=None, phone=None, dob=None):
        if not any([name, phone, dob]):
            raise ToolError("missing_identity", "Provide a name, phone or date of birth")
        if phone is not None and not re.fullmatch(r"\d{10}", phone):
            raise ToolError("invalid_phone", "phone must contain exactly 10 digits")
        if dob:
            valid_date(dob)
        words = set(normalise(name or "").split())
        candidates = [
            p
            for p in self.schedule.clinic["patients"]
            if (not words or words.issubset(set(normalise(p["name"]).split())))
            and (not phone or p["phone"] == phone)
            and (not dob or p["dob"] == dob)
        ]
        if len(candidates) == 1:
            self.resolved.add(candidates[0]["id"])
        ids = {p["id"] for p in candidates}
        appointments = [a for a in self.schedule.appointments() if a["patient_id"] in ids and a["status"] == "booked"]
        return {"ok": True, "candidates": candidates, "appointments": appointments, "unique": len(candidates) == 1}

    def search_slots(self, doctor_id, date):
        day = valid_date(date)
        doctors = [d for d in self.schedule.clinic["doctors"] if d["id"] == doctor_id]
        if not doctors:
            raise ToolError("unknown_doctor", "doctor_id does not identify a clinic doctor")
        doctor = doctors[0]
        reason = None
        if day < self.today:
            reason = "past_date"
        elif date in self.schedule.clinic["holidays"]:
            reason = "clinic_holiday"
        elif date in doctor["leave_dates"]:
            reason = "doctor_on_leave"
        windows = [w for w in doctor["windows"] if w["day"] == day.strftime("%a")]
        if not windows and not reason:
            reason = "closed_weekday"
        starts = set()
        if not reason:
            for window in windows:
                starts.update(range(minute(window["start"]), minute(window["end"]) - 14, 15))
        occupied = [
            a
            for a in self.schedule.appointments()
            if a["doctor_id"] == doctor_id and a["date"] == date and a["status"] == "booked"
        ]
        slots = [
            {"start": clock(s), "end": clock(s + 15)}
            for s in sorted(starts)
            if not any(s < minute(a["end"]) and s + 15 > minute(a["start"]) for a in occupied)
        ]
        return {
            "ok": True,
            "doctor_id": doctor_id,
            "doctor_name": doctor["name"],
            "date": date,
            "slots": slots,
            "unavailable_reason": reason or (None if slots else "fully_booked"),
        }

    def authorise(self, actor_id, patient_id):
        patients = {p["id"]: p for p in self.schedule.clinic["patients"]}
        if actor_id not in self.resolved or patient_id not in self.resolved:
            raise ToolError("identity_unresolved", "Resolve actor and target uniquely through lookup_patient first")
        actor = patients.get(actor_id)
        if not actor or patient_id not in patients:
            raise ToolError("unknown_patient", "Patient does not exist")
        if actor_id != patient_id and patient_id not in actor["guardian_of"]:
            raise ToolError("not_authorised", "Only the patient or an explicitly listed guardian may act")

    def _slot(self, doctor_id, date, start, ignore=None):
        minute(start)
        # Availability validation is internal, not another public tool invocation.
        availability = self.search_slots(doctor_id, date)
        if start not in {s["start"] for s in availability["slots"]}:
            old = next((a for a in self.schedule.appointments() if a["id"] == ignore), None)
            if old and all(old[k] == v for k, v in [("doctor_id", doctor_id), ("date", date), ("start", start)]):
                raise ToolError("unchanged_slot", "Choose a different slot to reschedule")
            raise ToolError(
                "slot_unavailable",
                availability["unavailable_reason"] or "Requested slot is occupied or outside opening hours",
            )
        return clock(minute(start) + 15)

    def _write(self, operation):
        with self.schedule.lock:
            self.schedule.db.execute("BEGIN IMMEDIATE")
            try:
                result = operation()
                self.schedule.db.execute("COMMIT")
                return {"ok": True, "appointment": result}
            except Exception:
                self.schedule.db.execute("ROLLBACK")
                raise

    def book_appointment(self, patient_id, actor_id, doctor_id, date, start):
        self.authorise(actor_id, patient_id)

        def operation():
            end = self._slot(doctor_id, date, start)
            rows = self.schedule.appointments()
            next_id = max((int(a["id"].split("_")[1]) for a in rows), default=0) + 1
            appointment = dict(
                id=f"ap_{next_id:04d}",
                patient_id=patient_id,
                doctor_id=doctor_id,
                date=date,
                start=start,
                end=end,
                status="booked",
            )
            self.schedule.db.execute(
                "INSERT INTO appointments VALUES(:id,:patient_id,:doctor_id,:date,:start,:end,:status)", appointment
            )
            return appointment

        return self._write(operation)

    def _owned(self, appointment_id, patient_id, actor_id):
        self.authorise(actor_id, patient_id)
        appointment = next((a for a in self.schedule.appointments() if a["id"] == appointment_id), None)
        if not appointment or appointment["patient_id"] != patient_id:
            raise ToolError("ownership_mismatch", "Appointment does not belong to the resolved patient")
        if appointment["status"] != "booked":
            raise ToolError("already_cancelled", "Appointment is already cancelled")
        if valid_date(appointment["date"]) < self.today:
            raise ToolError("past_appointment", "A past appointment cannot be changed")
        return appointment

    def cancel_appointment(self, appointment_id, patient_id, actor_id):
        def operation():
            appointment = self._owned(appointment_id, patient_id, actor_id)
            self.schedule.db.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appointment_id,))
            return {**appointment, "status": "cancelled"}

        return self._write(operation)

    def reschedule_appointment(self, appointment_id, patient_id, actor_id, doctor_id, date, start):
        def operation():
            old = self._owned(appointment_id, patient_id, actor_id)
            end = self._slot(doctor_id, date, start, ignore=appointment_id)
            self.schedule.db.execute(
                "UPDATE appointments SET doctor_id=?,date=?,start=?,end=? WHERE id=?",
                (doctor_id, date, start, end, appointment_id),
            )
            return {**old, "doctor_id": doctor_id, "date": date, "start": start, "end": end}

        return self._write(operation)

    def escalate_to_human(self, reason, detail):
        return {
            "ok": True,
            "reason": reason,
            "detail": detail,
            "status": "pending_human",
            "message": "A human clinician must review this now. Booking has stopped."
            if reason == "clinical_urgent"
            else "A human team member must review this request.",
        }
