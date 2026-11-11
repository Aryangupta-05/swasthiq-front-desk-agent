"""Deterministic orchestration over complete fixed caller scripts.

Safety preflight consumes every turn before mutations. Nonmutating availability
checks may run inline, but the commit barrier is the end of the supplied script.
"""

import re
import time
from .gemini import extractor
from .language import clinical_risk, corrected, dates, malicious, name_mentions, text, time_preference
from .models import RunResult
from .store import Schedule
from .tools import Tools, normalise


def run(request, schedule=None, model_extractor=None):
    started = time.perf_counter()
    own_schedule = schedule is None
    schedule = schedule or Schedule()
    before = schedule.appointments()
    tools = Tools(schedule, request.today)
    trace = []
    patient_id = None
    model = {"tokens": 0, "model": None, "status": "not_needed", "risk": "none"}

    def invoke(tool_name, **kwargs):
        result = tools.call(tool_name, **kwargs)
        trace.append(tools.events[-1])
        return result

    def say(value):
        trace.append({"type": "agent", "text": value})

    def finish(state, reply, reason=None, appointment=None):
        say(reply)
        result = RunResult(
            conversation_id=request.conversation_id,
            tool_calls=tools.calls,
            terminal_state=state,
            escalation_reason=reason,
            patient_id=patient_id,
            appointment_id=appointment["id"] if appointment else None,
            reply=reply,
            metrics={
                "turns": len(request.turns),
                "tokens": model["tokens"],
                "latency_ms": max(0, round((time.perf_counter() - started) * 1000)),
            },
        ).model_dump()
        unchanged = schedule.appointments() == before
        if state in ["escalated", "refused", "abandoned"] and not unchanged:
            raise RuntimeError("Safety invariant: a non-success outcome mutated the schedule")
        detail = {
            "result": result,
            "trace": trace,
            "model": {k: v for k, v in model.items() if k not in ["evidence", "risk"]},
            "schedule_unchanged": unchanged,
            "safety_preflight": "all caller turns checked before any mutation",
        }
        if own_schedule:
            schedule.close()
        return detail

    def escalate(reason, detail):
        output = invoke("escalate_to_human", reason=reason, detail=detail)
        return finish("escalated", output["message"], reason)

    # Read the whole script before calling any mutating tool. UI trace represents
    # this exact batch processing, rather than fabricating interactive dialogue.
    risk = clinical_risk(request.turns)
    attack = malicious(request.turns)
    combined = text(" ".join(request.turns))
    for index, turn in enumerate(request.turns):
        trace.append({"type": "caller", "text": turn, "turn": index + 1})
    if risk == "clinical_urgent":
        return escalate(risk, "Urgent symptoms in caller script; scheduling commit blocked")
    if attack:
        return finish(
            "refused",
            "I cannot perform bulk changes, disclose patient records, or accept administrative instructions from a caller.",
        )
    if risk:
        return escalate(risk, "Caller requested a clinical judgement or medication advice")
    model = (model_extractor or extractor).extract(request.turns)
    if model["risk"] != "none":
        return escalate(
            model["risk"], "Structured triage extraction found a clinical concern with literal caller evidence"
        )
    if re.search(r"\b(?:padosi|neighbou?r|acquaintance|friend|colleague)\b", combined):
        return escalate("not_authorised", "Caller identifies as a third party; no verified guardian authority")
    if re.search(r"\b(?:billing|insurance|refund|lab report|test result|invoice|ambulance|certificate)\b", combined):
        return escalate("out_of_scope", "Legitimate request outside appointment scheduling")

    intent = "book"
    intent_pattern = r"\b(book|cancel|cancellation|reschedul\w*|move|shift|postpone|karwana|appointment)\b"
    for raw in request.turns:
        value = corrected(raw)
        if re.search(r"\b(?:cancel|cancellation)\b", value):
            intent = "cancel"
        elif re.search(r"\b(?:reschedul\w*|move|shift|postpone)\b", value) or re.search(
            r"mera.*appointment.*(?:use|karwana)|aaj ka appointment.*(?:saturday|karwana)", value
        ):
            intent = "reschedule"
        elif re.search(r"\b(?:book|new appointment)\b", value):
            intent = "book"
    has_request = bool(re.search(intent_pattern + r"|milna hai|aa sakta|ke saath|ke paas|dikhana", combined))
    if not has_request:
        return finish("abandoned", "No actionable appointment request was received.")

    doctor_id = None
    day = None
    start = None
    window = None
    availability = None
    for raw in request.turns:
        value = corrected(raw)
        doctors = []
        for d in schedule.clinic["doctors"]:
            surname = normalise(d["name"]).split()[-1]
            if re.search(r"\b" + re.escape(surname) + r"\b", value):
                doctors.append(d["id"])
        if not doctors:
            doctors = [
                d["id"]
                for d in schedule.clinic["doctors"]
                if re.search(r"\b" + re.escape(normalise(d["name"]).split()[-1]) + r"\b", text(raw))
            ]
        if len(doctors) == 1:
            doctor_id = doctors[0]
        elif len(doctors) > 1:
            return escalate("out_of_scope", "Doctor preference is unresolved")
        date_values = dates(raw, request.today)
        old_day = day
        if date_values:
            day = date_values[-1]
        new_start, new_window = time_preference(raw)
        if new_start:
            start = new_start
        if new_window:
            window = new_window
        if day != old_day and doctor_id and day and day != "invalid" and intent != "cancel":
            # Real read-only tool results can precede identity resolution. They
            # are appended where executed, after the batch's caller transcript.
            availability = invoke("search_slots", doctor_id=doctor_id, date=day)

    if day == "invalid" or start == "invalid":
        return finish("abandoned", "The requested date or time is invalid. Please provide a valid date and HH:MM time.")

    patients = schedule.clinic["patients"]
    mentions = name_mentions(request.turns, patients)
    phones = re.findall(r"(?<!\d)\d{10}(?!\d)", combined)
    phone = phones[-1] if phones else None
    # Prefer explicit full-name identity in the same turn as the final phone.
    identified = []
    if phone:
        phone_turns = [i for i, t in enumerate(request.turns) if phone in t]
        identified = [p for i, _, p in mentions if i == phone_turns[-1] and p["phone"] == phone]
    if not identified and mentions:
        identified = [p for _, _, p in mentions if not phone or p["phone"] == phone]
    distinct = {p["id"]: p for p in identified}
    # Do not make a first-match choice if multiple names remain in the script.
    actor_name = next(iter(distinct.values()))["name"] if len(distinct) == 1 else None
    if len(distinct) > 1:
        return escalate("ambiguous_patient", "More than one caller identity remains unresolved")
    if not actor_name and not phone:
        words = set(normalise(combined).split())
        matched = sorted(
            {part for p in patients for part in normalise(p["name"]).split() if len(part) > 2 and part in words}
        )
        if matched:
            actor_name = " ".join(matched)
    if not actor_name and not phone:
        return finish("abandoned", "No patient identity was provided; no appointment was changed.")
    identity = invoke("lookup_patient", name=actor_name, phone=phone)
    candidates = identity.get("candidates", [])
    if len(candidates) != 1:
        return escalate("ambiguous_patient", "Patient identity could not be resolved uniquely")
    actor = candidates[0]
    target = actor
    target_lookup = identity
    # A phone shared by a family does not establish which family member is the
    # target. Names must resolve explicitly, then listed guardianship is checked.
    others = []
    for p in patients:
        if p["id"] == actor["id"]:
            continue
        first = normalise(p["name"]).split()[0]
        positions = [
            (i, text(t).find(first))
            for i, t in enumerate(request.turns)
            if re.search(r"\b" + re.escape(first) + r"\b", text(t))
        ]
        if positions:
            others.append((positions[-1], p))
    if others:
        # Common first names shared with the caller are not different targets.
        others = [
            (pos, p) for pos, p in others if normalise(p["name"]).split()[0] != normalise(actor["name"]).split()[0]
        ]
    if others:
        unique_others = {p["id"]: p for _, p in others}
        if len(unique_others) > 1:
            # A specific later correction can resolve a child; "Aarav or Arjun"
            # in one turn remains ambiguous.
            last_turn = max(pos[0] for pos, _ in others)
            latest = {p["id"]: p for pos, p in others if pos[0] == last_turn}
            if len(latest) != 1:
                return escalate("ambiguous_patient", "More than one named target remains")
            target = next(iter(latest.values()))
        else:
            target = next(iter(unique_others.values()))
        if target["id"] not in actor["guardian_of"]:
            return escalate("not_authorised", "Resolved caller is not the target or a listed guardian")
        target_lookup = invoke("lookup_patient", name=target["name"], phone=target["phone"])
        if not target_lookup.get("unique"):
            return escalate("ambiguous_patient", "Dependent identity could not be resolved uniquely")
    if not phone:
        # A unique name is identification but not a sufficient synthetic proof
        # of authority. Real deployments must replace this with verified auth.
        return escalate("not_authorised", "A matching phone and name are required for a record operation")
    patient_id = target["id"]
    owned = [a for a in target_lookup["appointments"] if a["date"] >= request.today]
    if intent in ["cancel", "reschedule"]:
        appointments = owned
        explicit_ids = re.findall(r"\bap_\d{4,}\b", combined)
        if explicit_ids:
            appointments = [a for a in owned if a["id"] == explicit_ids[-1]]
            if not appointments:
                return escalate(
                    "not_authorised", "The requested appointment ID is not in the resolved patient's owned appointments"
                )
        elif intent == "cancel" and day:
            appointments = [a for a in owned if a["date"] == day]
        elif "aaj" in combined or "today" in combined:
            appointments = [a for a in owned if a["date"] == request.today]
        if len(appointments) != 1:
            return escalate(
                "ambiguous_patient" if len(appointments) > 1 else "out_of_scope",
                "No single owned appointment was identified",
            )
        appointment = appointments[0]
        if intent == "cancel":
            output = invoke(
                "cancel_appointment", appointment_id=appointment["id"], patient_id=patient_id, actor_id=actor["id"]
            )
            if output["ok"]:
                return finish(
                    "cancelled",
                    f"Appointment {output['appointment']['id']} is cancelled.",
                    appointment=output["appointment"],
                )
            return finish("abandoned", output["error"]["message"])
        doctor_id = doctor_id or appointment["doctor_id"]
    if not doctor_id or not day:
        return finish("abandoned", "A doctor and a date are required before an appointment can be committed.")
    if not availability or availability.get("doctor_id") != doctor_id or availability.get("date") != day:
        availability = invoke("search_slots", doctor_id=doctor_id, date=day)
    slots = availability.get("slots", [])
    if window:
        slots = [s for s in slots if (s["start"] < "12:00" if window == "morning" else s["start"] >= "16:00")]
    if start:
        slots = [s for s in slots if s["start"] == start]
    if not slots:
        message = availability.get("unavailable_reason") or "Requested time is not available"
        return finish("abandoned", f"No appointment was changed. {message}. Please choose another date or time.")
    kwargs = dict(patient_id=patient_id, actor_id=actor["id"], doctor_id=doctor_id, date=day, start=slots[0]["start"])
    name = "book_appointment"
    state = "booked"
    if intent == "reschedule":
        name, state = "reschedule_appointment", "rescheduled"
        kwargs["appointment_id"] = appointment["id"]
    output = invoke(name, **kwargs)
    if not output["ok"]:
        return finish("abandoned", output["error"]["message"])
    a = output["appointment"]
    return finish(
        state,
        f"Appointment {a['id']} {state}: {availability['doctor_name']}, {a['date']} at {a['start']} (Asia/Kolkata).",
        appointment=a,
    )
