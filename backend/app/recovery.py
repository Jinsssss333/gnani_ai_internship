"""Local supervisor recovery; deliberately excluded from the public phone gateway."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app import db
from app.call_flow import next_question
from app.questions import question

router = APIRouter()


def required_state(answers):
    field = 'visit_done'
    while field != 'FINAL_REVIEW':
        answer = answers.get(field, {})
        if answer.get('awaiting_replacement') or not (answer.get('confirmed') or
                (answer.get('unresolved') and question(field).get('optional'))):
            return field
        field = next_question(field, answer.get('value'))
    return field


@router.get('/api/register/sessions')
def sessions():
    with db.connect() as conn:
        rows = conn.execute('SELECT id FROM call_sessions WHERE status != ? ORDER BY updated_at DESC', ('completed',)).fetchall()
        active = {r[0] for r in conn.execute("SELECT session_id FROM phone_calls WHERE ended_at IS NULL")}
    result = []
    for row in rows:
        session = db.get_call_session(row[0])
        session['record_status'] = 'in_progress' if row[0] in active and session['status'] != 'draft' else 'needs_review'
        session['missing_field'] = required_state(session['answers'])
        result.append(session)
    return result


class Repair(BaseModel):
    field: str
    text: str


@router.post('/api/register/sessions/{session_id}/answer')
def repair(session_id: str, payload: Repair):
    from app.main import _read_answer
    session = db.get_call_session(session_id)
    if not session:
        raise HTTPException(404, 'Session not found')
    with db.connect() as conn:
        active = conn.execute('SELECT 1 FROM phone_calls WHERE session_id=? AND ended_at IS NULL', (session_id,)).fetchone()
    if active or session['status'] == 'completed':
        raise HTTPException(409, 'Wait until the call ends before editing.')
    if payload.field != required_state(session['answers']):
        raise HTTPException(409, 'Refresh and resolve the next missing field.')
    item = question(payload.field)
    raw = payload.text.strip()
    skipped = not raw and item.get('optional', False)
    if skipped:
        value = None
    elif item['type'] == 'date_phrase':
        try:
            date = datetime.strptime(raw, '%Y-%m-%d').date()
            if date < datetime.now(timezone(timedelta(hours=5, minutes=30))).date():
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Choose today or a future follow-up date.')
        value = {'date': date.isoformat(), 'phrase': raw}
    else:
        value, _ = _read_answer(item, raw, None)
    previous = session['answers'].get(payload.field)
    session['answers'][payload.field] = {
        'answer_id': str(uuid4()), 'question_id': payload.field, 'value': value,
        'transcript': raw, 'evidence_quote': raw, 'confirmed': True,
        'needs_confirmation': False, 'unresolved': skipped, 'extraction_source': 'supervisor',
        'previous_attempts': ([*previous.get('previous_attempts', []), {k:v for k,v in previous.items() if k != 'previous_attempts'}] if previous else []),
    }
    session['current_question_id'] = required_state(session['answers'])
    session['status'] = 'draft'
    db.update_call_session(session)
    db.record_audit_event({'id': str(uuid4()), 'visit_id': session_id,
        'occurred_at': datetime.now(timezone.utc).isoformat(), 'action': 'updated',
        'summary': f'Supervisor confirmed {payload.field}.', 'actor': 'Supervisor'})
    return session
