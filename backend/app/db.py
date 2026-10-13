import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _database_path() -> Path:
    configured = Path(os.getenv("DATABASE_PATH", "./data/visits.db"))
    if not configured.is_absolute():
        configured = Path(__file__).resolve().parents[1] / configured
    configured.parent.mkdir(parents=True, exist_ok=True)
    return configured


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(_database_path())
    db.row_factory = sqlite3.Row
    return db


def initialize() -> None:
    with connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS visits (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                transcript TEXT NOT NULL,
                language TEXT NOT NULL,
                extraction_source TEXT NOT NULL,
                visit_json TEXT NOT NULL
            )"""
        )


def save_visit(
    transcript: str,
    language: str,
    extraction_source: str,
    visit: dict,
    visit_id: str | None = None,
    created_at: str | None = None,
) -> dict:
    visit_id = visit_id or str(uuid4())
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO visits (id, created_at, transcript, language, extraction_source, visit_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET transcript=excluded.transcript, language=excluded.language,
            extraction_source=excluded.extraction_source, visit_json=excluded.visit_json""",
            (visit_id, created_at, transcript, language, extraction_source, json.dumps(visit)),
        )
    return {
        "id": visit_id,
        "created_at": created_at,
        "transcript": transcript,
        "language": language,
        "extraction_source": extraction_source,
        "visit": visit,
    }


def list_visits(limit: int = 50) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, created_at, transcript, language, extraction_source, visit_json FROM visits ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "transcript": row["transcript"],
            "language": row["language"],
            "extraction_source": row["extraction_source"],
            "visit": json.loads(row["visit_json"]),
        }
        for row in rows
    ]
