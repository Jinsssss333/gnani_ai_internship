"""Shared question definitions used by the call-flow API and offline client."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def load_questions() -> dict[str, dict]:
    path = Path(__file__).resolve().parents[2] / "shared" / "questions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {question["id"]: question for question in payload["flow"]}


def question(question_id: str) -> dict:
    try:
        return load_questions()[question_id]
    except KeyError as exc:
        raise ValueError(f"Unknown question: {question_id}") from exc


def prompt(question_id: str) -> dict:
    item = question(question_id)
    return {
        "id": item["id"],
        "text": item["prompt"],
        "audio_url": None,
        "expects": {
            "type": item["type"],
            "keypad": item.get("keypad") or item.get("options"),
            "optional": item.get("optional", False),
        },
    }
