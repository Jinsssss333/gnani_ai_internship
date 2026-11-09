from pydantic import BaseModel, ConfigDict, Field


class Vitals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    blood_pressure: str | None = None
    temperature_f: float | None = None


class VisitFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    vitals: Vitals = Field(default_factory=Vitals)
    symptoms: list[str] = Field(default_factory=list)
    follow_up_date: str | None = None
    follow_up_phrase: str | None = None
    follow_up_status: str | None = None
    notes: str | None = None


class ConfirmVisit(BaseModel):
    id: str | None = None
    created_at: str | None = None
    transcript: str
    language: str = "hi-IN"
    visit: VisitFields
    extraction_source: str = "unknown"
    deleted_at: str | None = None


class AuditEvent(BaseModel):
    id: str
    visit_id: str
    occurred_at: str
    action: str
    summary: str
    actor: str = "Demo ASHA worker"


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: str = "hi-IN"


class CallStartRequest(BaseModel):
    language_code: str = "hi-IN"
    visit_code: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class CallAnswerRequest(BaseModel):
    answer_id: str = Field(min_length=1, max_length=100)
    question_id: str
    text: str | None = Field(default=None, max_length=500)
    dtmf: str | None = Field(default=None, max_length=1)


class CallActionRequest(BaseModel):
    action: str = Field(pattern=r"^(confirm|correct|repeat|skip|unresolved)$")
    field: str | None = None
