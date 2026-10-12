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
    notes: str | None = None


class ConfirmVisit(BaseModel):
    transcript: str
    language: str = "hi-IN"
    visit: VisitFields
    extraction_source: str = "unknown"


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: str = "hi-IN"
