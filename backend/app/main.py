import os
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
from app.providers import evon, prisma, timbre
from app.schemas import ConfirmVisit, TtsRequest


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    yield


app = FastAPI(title="SwarSathi API", version="0.1.0", lifespan=lifespan)
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "providers": {
            "prisma": bool(os.getenv("PRISMA_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID")),
            "evon": bool(os.getenv("EVON_CHAT_COMPLETIONS_URL") or os.getenv("EVON_INFERENCE_ENDPOINT")),
            "timbre": bool(os.getenv("TIMBRE_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID")),
        },
    }


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
    )


@app.get("/api/visits")
async def get_visits() -> list[dict]:
    return db.list_visits()


@app.post("/api/tts")
async def text_to_speech(payload: TtsRequest) -> Response:
    try:
        audio, content_type = await timbre.synthesize(payload.text, payload.language)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Timbre provider error: {exc}") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type=content_type)
