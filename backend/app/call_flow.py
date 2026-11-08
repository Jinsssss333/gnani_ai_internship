"""Pure transition helpers for SunoCare's guided visit flow."""

from app.questions import question


FINAL_REVIEW = "FINAL_REVIEW"
SAVED = "SAVED"


def next_question(question_id: str, value: object) -> str:
    item = question(question_id)
    target = item.get("next", FINAL_REVIEW)
    if isinstance(target, dict):
        key = str(value).lower()
        return target[key]
    return target


def allowed_action(question_id: str, action: str) -> bool:
    if action in {"confirm", "correct", "repeat"}:
        return True
    return action in {"skip", "unresolved"} and bool(question(question_id).get("optional"))
