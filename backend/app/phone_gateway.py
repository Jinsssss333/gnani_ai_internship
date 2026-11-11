"""Public phone entry point; supervisor and legacy write APIs stay on the local app."""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import db
from app.telephony import exotel


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    yield


app = FastAPI(title="SunoCare phone gateway", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_api_websocket_route("/api/telephony/exotel", exotel)


@app.get("/health")
async def health():
    return {"status": "ok"}
