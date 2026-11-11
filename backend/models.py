"""Strict evaluation contract and tool inputs; strings remain strings in the wire format."""

from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

State = Literal["booked", "rescheduled", "cancelled", "escalated", "refused", "abandoned"]
Reason = Literal["clinical_urgent", "medical_advice", "not_authorised", "ambiguous_patient", "out_of_scope"]
ToolName = Literal[
    "search_slots",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "lookup_patient",
    "escalate_to_human",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RunRequest(StrictModel):
    conversation_id: StrictStr = Field(min_length=1, max_length=128)
    today: StrictStr
    turns: list[StrictStr] = Field(max_length=100)

    @field_validator("today")
    @classmethod
    def valid_today(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("today must be a valid YYYY-MM-DD date")
        return value

    @field_validator("turns")
    @classmethod
    def bounded_turns(cls, value):
        if any(len(t) > 4000 for t in value) or sum(map(len, value)) > 30000:
            raise ValueError("limit is 4000 characters per turn and 30000 per conversation")
        return value


class ToolCall(StrictModel):
    name: ToolName
    arguments: dict[str, Any]


class Metrics(StrictModel):
    turns: StrictInt = Field(ge=0)
    tokens: StrictInt = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)


class RunResult(StrictModel):
    conversation_id: StrictStr
    tool_calls: list[ToolCall]
    terminal_state: State
    escalation_reason: Reason | None
    patient_id: StrictStr | None
    appointment_id: StrictStr | None
    reply: StrictStr
    metrics: Metrics

    @model_validator(mode="after")
    def consistent_reason(self):
        if (self.terminal_state == "escalated") != (self.escalation_reason is not None):
            raise ValueError("escalation_reason is required only for escalated")
        return self


class Lookup(StrictModel):
    name: StrictStr | None = None
    phone: StrictStr | None = None
    dob: StrictStr | None = None


class Search(StrictModel):
    doctor_id: StrictStr
    date: StrictStr


class Book(Search):
    patient_id: StrictStr
    actor_id: StrictStr
    start: StrictStr


class Move(Book):
    appointment_id: StrictStr


class Cancel(StrictModel):
    appointment_id: StrictStr
    patient_id: StrictStr
    actor_id: StrictStr


class Escalate(StrictModel):
    reason: Reason
    detail: StrictStr = Field(min_length=1, max_length=2000)
