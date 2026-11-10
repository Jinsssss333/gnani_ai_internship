import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _database_path() -> Path:
    configured = Path(os.getenv("DATABASE_PATH", "./data/visits.db"))
    if not configured.is_absolute():
        configured = Path(__file__).resolve().parents[1] / configured
    configured.parent.mkdir(parents=True, exist_ok=True)
    return configured


@contextmanager
def connect():
    db = sqlite3.connect(_database_path())
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS phone_calls (
            call_sid TEXT PRIMARY KEY, session_id TEXT, started_at TEXT NOT NULL,
            ended_at TEXT, status TEXT NOT NULL)""")
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
        db.execute(
            """CREATE TABLE IF NOT EXISTS visit_cards (
                code TEXT PRIMARY KEY,
                label TEXT NOT NULL
            )"""
        )
        db.executemany(
            "INSERT OR IGNORE INTO visit_cards (code, label) VALUES (?, ?)",
            [
                ("4821", "Synthetic household #21"),
                ("4822", "Synthetic household #22"),
                ("7304", "Synthetic household #04"),
            ],
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS call_sessions (
                id TEXT PRIMARY KEY,
                language_code TEXT NOT NULL,
                visit_code TEXT NOT NULL,
                current_question_id TEXT NOT NULL,
                status TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finalization_json TEXT
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


def visit_card(code: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT code, label FROM visit_cards WHERE code = ?", (code,)).fetchone()
    return dict(row) if row else None


def create_call_session(language_code: str, visit_code: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "id": str(uuid4()),
        "language_code": language_code,
        "visit_code": visit_code,
        "current_question_id": "visit_done",
        "status": "in_progress",
        "answers": {},
        "created_at": now,
        "updated_at": now,
        "finalization": None,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO call_sessions
            (id, language_code, visit_code, current_question_id, status, answers_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session["id"], session["language_code"], session["visit_code"],
                session["current_question_id"], session["status"], json.dumps(session["answers"]),
                now, now,
            ),
        )
    return session


def get_call_session(session_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM call_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "language_code": row["language_code"], "visit_code": row["visit_code"],
        "current_question_id": row["current_question_id"], "status": row["status"],
        "answers": json.loads(row["answers_json"]), "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "finalization": json.loads(row["finalization_json"]) if row["finalization_json"] else None,
    }


def update_call_session(session: dict) -> dict:
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute(
            """UPDATE call_sessions SET current_question_id = ?, status = ?, answers_json = ?,
            updated_at = ?, finalization_json = ? WHERE id = ?""",
            (
                session["current_question_id"], session["status"], json.dumps(session["answers"]),
                session["updated_at"], json.dumps(session["finalization"]) if session.get("finalization") else None,
                session["id"],
            ),
        )
    return session


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


def finalize_call(session_id: str) -> dict:
    """Validate the actual branch and commit the visit, audit and receipt atomically."""
    from app.call_flow import next_question
    from app.questions import question

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise ValueError("Call session not found.")
        if row["finalization_json"]:
            return json.loads(row["finalization_json"])
        if row["current_question_id"] != "FINAL_REVIEW":
            raise ValueError("Complete the review before saving.")
        answers = json.loads(row["answers_json"])
        active = {}
        field = "visit_done"
        while field != "FINAL_REVIEW":
            answer = answers.get(field)
            optional_skip = answer and answer.get("unresolved") and question(field).get("optional")
            if not answer or answer.get("awaiting_replacement") or not (answer.get("confirmed") or optional_skip):
                raise ValueError(f"Confirm {field} before saving.")
            active[field] = answer
            field = next_question(field, answer["value"])
        value = lambda key: active.get(key, {}).get("value")
        symptoms = value("symptoms") or {}
        reported = symptoms.get("reported", [])
        followup = value("followup_date")
        visit = {
            "patient_name": value("patient_name"), "age": value("age"),
            "vitals": {"blood_pressure": None, "temperature_f": None},
            "symptoms": reported if isinstance(reported, list) else [reported],
            "negated_symptoms": symptoms.get("negated", []),
            "follow_up_phrase": followup.get("phrase") if isinstance(followup, dict) else followup,
            "follow_up_date": followup.get("date") if isinstance(followup, dict) else None,
            "notes": value("notes"), "visit_code": row["visit_code"],
            "visit_status": "completed" if value("visit_done") else "not_completed",
            "review_status": "confirmed", "sync_status": "synced", "evidence": active,
        }
        transcript = "\n".join(f"{key}: {answer['transcript']}" for key, answer in active.items())
        saved = {"id": session_id, "created_at": row["created_at"], "transcript": transcript,
                 "language": row["language_code"], "extraction_source": "guided-worker-confirmed",
                 "visit": visit, "deleted_at": None}
        conn.execute("INSERT INTO visits (id, created_at, transcript, language, extraction_source, visit_json, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (session_id, row["created_at"], transcript, row["language_code"],
                      saved["extraction_source"], json.dumps(visit), None))
        now = datetime.now(timezone.utc).isoformat()
        audit = {"id": f"finalize-{session_id}", "visit_id": session_id, "occurred_at": now,
                 "action": "created", "summary": f"Call visit {row['visit_code']} confirmed; evidence retained.",
                 "actor": "Demo worker (synthetic)"}
        conn.execute("INSERT INTO audit_events (id, visit_id, occurred_at, action, summary, actor) VALUES (?, ?, ?, ?, ?, ?)", tuple(audit.values()))
        result = {"visit": saved, "audit": audit}
        conn.execute("UPDATE call_sessions SET status='completed', current_question_id='SAVED', updated_at=?, finalization_json=? WHERE id=?",
                     (now, json.dumps(result), session_id))
        return result


def start_phone_call(call_sid: str) -> bool:
    with connect() as conn:
        return conn.execute("INSERT OR IGNORE INTO phone_calls (call_sid, started_at, status) VALUES (?, ?, 'connected')",
                            (call_sid, datetime.now(timezone.utc).isoformat())).rowcount == 1


def link_phone_call(call_sid: str, session_id: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE phone_calls SET session_id=? WHERE call_sid=?", (session_id, call_sid))


def end_phone_call(call_sid: str) -> None:
    with connect() as conn:
        conn.execute("""UPDATE phone_calls SET ended_at=?, status=CASE WHEN
            EXISTS(SELECT 1 FROM call_sessions WHERE id=phone_calls.session_id AND status='completed')
            THEN 'completed' ELSE 'ended_incomplete' END WHERE call_sid=?""",
            (datetime.now(timezone.utc).isoformat(), call_sid))


def list_phone_calls() -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM phone_calls ORDER BY started_at DESC LIMIT 50")]
