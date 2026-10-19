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
                visit_json TEXT NOT NULL,
                deleted_at TEXT
            )"""
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(visits)").fetchall()}
        if "deleted_at" not in columns:
            db.execute("ALTER TABLE visits ADD COLUMN deleted_at TEXT")
        db.execute(
            """CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                action TEXT NOT NULL,
                summary TEXT NOT NULL,
                actor TEXT NOT NULL
            )"""
        )


def save_visit(
    transcript: str,
    language: str,
    extraction_source: str,
    visit: dict,
    visit_id: str | None = None,
    created_at: str | None = None,
    deleted_at: str | None = None,
) -> dict:
    visit_id = visit_id or str(uuid4())
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """INSERT INTO visits (id, created_at, transcript, language, extraction_source, visit_json, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET transcript=excluded.transcript, language=excluded.language,
            extraction_source=excluded.extraction_source, visit_json=excluded.visit_json,
            deleted_at=excluded.deleted_at""",
            (visit_id, created_at, transcript, language, extraction_source, json.dumps(visit), deleted_at),
        )
    return {
        "id": visit_id,
        "created_at": created_at,
        "transcript": transcript,
        "language": language,
        "extraction_source": extraction_source,
        "visit": visit,
        "deleted_at": deleted_at,
    }


def list_visits(limit: int = 100, include_deleted: bool = False) -> list[dict]:
    where = "" if include_deleted else "WHERE deleted_at IS NULL"
    with connect() as db:
        rows = db.execute(
            f"SELECT id, created_at, transcript, language, extraction_source, visit_json, deleted_at FROM visits {where} ORDER BY created_at DESC LIMIT ?",
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
            "deleted_at": row["deleted_at"],
        }
        for row in rows
    ]


def soft_delete_visit(visit_id: str, deleted_at: str | None = None) -> bool:
    deleted_at = deleted_at or datetime.now(timezone.utc).isoformat()
    with connect() as db:
        cursor = db.execute(
            "UPDATE visits SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (deleted_at, visit_id),
        )
        return cursor.rowcount > 0


def record_audit_event(event: dict) -> dict:
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO audit_events (id, visit_id, occurred_at, action, summary, actor) VALUES (?, ?, ?, ?, ?, ?)",
            (event["id"], event["visit_id"], event["occurred_at"], event["action"], event["summary"], event["actor"]),
        )
    return event


def list_audit_events(limit: int = 200) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, visit_id, occurred_at, action, summary, actor FROM audit_events ORDER BY occurred_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
