import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import db
from app.call_flow import FINAL_REVIEW, allowed_action, next_question
from app.questions import prompt, question
from app.providers import evon, prisma, timbre
from app.schemas import (
    AuditEvent,
    CallActionRequest,
    CallAnswerRequest,
    CallStartRequest,
    ConfirmVisit,
    TtsRequest,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    yield


app = FastAPI(title="SunoCare API", version="0.2.0", lifespan=lifespan)
origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mode": os.getenv("PROVIDER_MODE", "live").strip().lower(),
        "providers": {
            "prisma": bool(os.getenv("PRISMA_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID")),
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
            "evon": bool(os.getenv("EVON_CHAT_COMPLETIONS_URL") or os.getenv("EVON_INFERENCE_ENDPOINT")),
            "timbre": bool(os.getenv("TIMBRE_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID")),
        },
    }


def _session_or_404(session_id: str) -> dict:
    session = db.get_call_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session was not found.")
    return session


def _read_answer(item: dict, text: str | None, dtmf: str | None) -> tuple[object, str]:
    raw = (dtmf or text or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="Provide an answer using text or keypad input.")
    kind = item["type"]
    if kind == "boolean":
        values = {"1": True, "yes": True, "y": True, "haan": True, "ha": True, "2": False, "no": False, "n": False, "nahi": False}
        value = values.get(raw.lower())
        if value is None:
            raise HTTPException(status_code=422, detail="Choose 1 for yes or 2 for no.")
        return value, raw
    if kind == "enum":
        value = item["options"].get(raw)
        if value is None:
            raise HTTPException(status_code=422, detail="Choose one of the displayed options.")
        return value, raw
    if kind == "integer":
        match = re.search(r"\b\d{1,3}\b", raw)
        if not match:
            raise HTTPException(status_code=422, detail="Enter the age as digits for this first demo flow.")
        value = int(match.group())
        if not item["min"] <= value <= item["max"]:
            raise HTTPException(status_code=422, detail="Age must be between 0 and 120.")
        return value, match.group()
    if kind == "symptoms":
        return {"reported": raw, "negated": []}, raw
    return raw, raw


def _session_response(session: dict, *, answer: dict | None = None) -> dict:
    response = {
        "session_id": session["id"],
        "state": session["current_question_id"],
        "status": session["status"],
        "visit_code": session["visit_code"],
        "answers": session["answers"],
    }
    if session["current_question_id"] not in {FINAL_REVIEW, "SAVED"}:
        response["prompt"] = prompt(session["current_question_id"])
    if answer:
        response["answer"] = answer
    return response


@app.post("/api/calls/start")
async def start_call(payload: CallStartRequest) -> dict:
    card = db.visit_card(payload.visit_code)
    if not card:
        raise HTTPException(status_code=404, detail="visit_code_not_found")
    session = db.create_call_session(payload.language_code, payload.visit_code)
    result = _session_response(session)
    result["visit_card"] = card
    return result


@app.get("/api/calls/{session_id}")
async def get_call(session_id: str) -> dict:
    return _session_response(_session_or_404(session_id))


@app.post("/api/calls/{session_id}/answer")
async def answer_call(session_id: str, payload: CallAnswerRequest) -> dict:
    session = _session_or_404(session_id)
    current_id = session["current_question_id"]
    if current_id in {FINAL_REVIEW, "SAVED"}:
        raise HTTPException(status_code=409, detail="This call is ready for final review.")
    if payload.question_id != current_id:
        raise HTTPException(status_code=409, detail="Answer the current question before continuing.")
    existing = session["answers"].get(current_id)
    submitted = (payload.dtmf or payload.text or "").strip()
    if existing and existing["answer_id"] == payload.answer_id:
        if existing["transcript"] != submitted:
            raise HTTPException(status_code=409, detail="This answer ID was already used with different content.")
        return _session_response(session, answer=existing)
    item = question(current_id)
    value, evidence = _read_answer(item, payload.text, payload.dtmf)
    attempt = (existing or {}).get("attempt", 0) + 1
    answer = {
        "answer_id": payload.answer_id,
        "question_id": current_id,
        "attempt": attempt,
        "transcript": submitted,
        "value": value,
        "evidence_quote": evidence,
        "extraction_source": "intent" if item["type"] in {"boolean", "enum", "integer"} else "worker-text",
        "needs_confirmation": True,
        "confirmed": False,
    }
    session["answers"][current_id] = answer
    db.update_call_session(session)
    return _session_response(session, answer=answer)


@app.post("/api/calls/{session_id}/action")
async def call_action(session_id: str, payload: CallActionRequest) -> dict:
    session = _session_or_404(session_id)
    current_id = session["current_question_id"]
    if current_id in {FINAL_REVIEW, "SAVED"}:
        raise HTTPException(status_code=409, detail="This call is already ready for finalization.")
    if not allowed_action(current_id, payload.action):
        raise HTTPException(status_code=422, detail="That action is not available for this question.")
    answer = session["answers"].get(current_id)
    if payload.action == "confirm":
        if not answer:
            raise HTTPException(status_code=409, detail="Record an answer before confirming it.")
        answer["confirmed"] = True
        answer["needs_confirmation"] = False
        session["current_question_id"] = next_question(current_id, answer["value"])
    elif payload.action == "skip":
        session["answers"][current_id] = {
            "answer_id": f"skipped-{current_id}", "question_id": current_id,
            "attempt": 0, "transcript": "", "value": None, "evidence_quote": "",
            "extraction_source": "worker", "needs_confirmation": False, "confirmed": False,
            "unresolved": True,
        }
        session["current_question_id"] = next_question(current_id, None)
    elif payload.action == "unresolved":
        session["current_question_id"] = next_question(current_id, answer["value"] if answer else None)
    # correct/repeat intentionally retain the existing answer as an audit-worthy attempt.
    db.update_call_session(session)
    return _session_response(session)


@app.post("/api/calls/{session_id}/finalize")
async def finalize_call(session_id: str) -> dict:
    session = _session_or_404(session_id)
    if session.get("finalization"):
        return session["finalization"]
    if session["current_question_id"] != FINAL_REVIEW:
        raise HTTPException(status_code=409, detail="Confirm the guided answers before finalizing.")
    outstanding = [
        answer["question_id"] for answer in session["answers"].values()
        if not answer.get("confirmed") and not answer.get("unresolved")
    ]
    if outstanding:
        raise HTTPException(status_code=409, detail=f"These answers still need review: {', '.join(outstanding)}")
    answers = session["answers"]
    symptoms = answers.get("symptoms", {}).get("value") or {}
    visit = {
        "patient_name": None,
        "age": answers.get("age", {}).get("value"),
        "vitals": {"blood_pressure": None, "temperature_f": None},
        "symptoms": [symptoms["reported"]] if symptoms.get("reported") else [],
        "follow_up_date": None,
        "follow_up_phrase": answers.get("followup_date", {}).get("value"),
        "notes": answers.get("notes", {}).get("value"),
        "visit_status": "completed" if answers.get("visit_done", {}).get("value") else "not_completed",
        "review_status": "confirmed",
        "sync_status": "synced",
    }
    saved = db.save_visit(
        transcript="Guided SunoCare visit",
        language=session["language_code"],
        extraction_source="guided-worker-confirmed",
        visit=visit,
        visit_id=session["id"],
        created_at=session["created_at"],
    )
    audit = db.record_audit_event({
        "id": str(uuid4()), "visit_id": saved["id"],
        "occurred_at": datetime.now(timezone.utc).isoformat(), "action": "created",
        "summary": f"Guided visit {session['visit_code']} confirmed by worker.",
        "actor": "Demo ASHA worker",
    })
    result = {"visit": saved, "audit": audit}
    session["status"] = "completed"
    session["current_question_id"] = "SAVED"
    session["finalization"] = result
    db.update_call_session(session)
    return result


@app.post("/api/visits/process")
async def process_audio(
    audio_file: UploadFile = File(...),
    language: str = Form(os.getenv("GNANI_DEFAULT_LANG", "hi-IN")),
) -> dict:
    audio = await audio_file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    if len(audio) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Recording must be smaller than 20 MB.")
    try:
        transcript = await prisma.transcribe(
            audio,
            audio_file.filename or "visit-audio.webm",
            audio_file.content_type or "audio/webm",
            language,
        )
        visit, source = await evon.extract(transcript, language)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Model provider error: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript,
        "language": language,
        "extraction_source": source,
        "visit": visit.model_dump(),
    }


@app.post("/api/visits/demo")
async def demo_visit() -> dict:
    return {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "transcript": "Amina, 26 years old, blood pressure 120/80, temperature 98.6, mild fever and nausea, follow-up on Friday.",
        "language": "hi-IN",
        "extraction_source": "synthetic-demo",
        "visit": {
            "patient_name": "Amina",
            "age": 26,
            "vitals": {"blood_pressure": "120/80", "temperature_f": 98.6},
            "symptoms": ["mild fever", "nausea"],
            "follow_up_date": None,
            "follow_up_phrase": "Friday",
            "notes": None,
        },
    }


@app.post("/api/visits")
async def confirm_visit(payload: ConfirmVisit) -> dict:
    return db.save_visit(
        transcript=payload.transcript,
        language=payload.language,
        extraction_source=payload.extraction_source,
        visit=payload.visit.model_dump(),
        visit_id=payload.id,
        created_at=payload.created_at,
        deleted_at=payload.deleted_at,
    )


@app.get("/api/visits")
async def get_visits() -> list[dict]:
    return db.list_visits()


@app.delete("/api/visits/{visit_id}")
async def delete_visit(visit_id: str) -> dict:
    if not db.soft_delete_visit(visit_id):
        raise HTTPException(status_code=404, detail="Visit was not found or is already deleted.")
    return {"status": "deleted", "id": visit_id}


@app.get("/api/audit")
async def get_audit_events() -> list[dict]:
    return db.list_audit_events()


@app.post("/api/audit")
async def create_audit_event(payload: AuditEvent) -> dict:
    return db.record_audit_event(payload.model_dump())


@app.post("/api/tts")
async def text_to_speech(payload: TtsRequest) -> Response:
    try:
        audio, content_type = await timbre.synthesize(payload.text, payload.language)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Timbre provider error: {exc}") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type=content_type)
