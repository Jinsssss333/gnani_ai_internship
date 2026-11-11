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


def active_fields(answers: dict) -> list[str]:
    fields = []
    field = 'visit_done'
    while field != FINAL_REVIEW:
        fields.append(field)
        answer = answers.get(field)
        if isinstance(question(field).get('next'), dict) and not answer:
            break
        field = next_question(field, answer.get('value') if answer else None)
    return fields


def first_unresolved(answers: dict) -> str:
    for field in active_fields(answers):
        answer = answers.get(field, {})
        optional_skip = answer.get('unresolved') and question(field).get('optional')
        if answer.get('awaiting_replacement') or not (answer.get('confirmed') or optional_skip):
            return field
    return FINAL_REVIEW
