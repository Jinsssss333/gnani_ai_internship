import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app import db
from app.main import app
from app.phone_flow import PhoneConversation


class RecoveryTests(unittest.TestCase):
    def test_rejected_name_keeps_transcript_without_accepting_it(self):
        async def scenario():
            phone = PhoneConversation(AsyncMock())
            for digit in '41482111':
                await phone.digit(digit)
            phone.add_audio(b'\0\0' * 8000)
            with patch.dict(os.environ, {'AUDIO_STORAGE_PATH': self.temp.name + '/audio'}), patch(
                'app.phone_flow.prisma.transcribe', AsyncMock(return_value='akash e')), patch(
                'app.phone_flow.extract_field', AsyncMock(side_effect=ValueError('unclear'))):
                await phone.digit('1')
            saved = db.get_call_session(phone.session['session_id'])['answers']['patient_name']
            self.assertEqual(saved['transcript'], 'akash e')
            self.assertEqual(saved['failure_stage'], 'extraction')
            self.assertTrue(saved['awaiting_replacement'])
            self.assertIsNone(saved['value'])
            self.assertFalse(saved['confirmed'])
        asyncio.run(scenario())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'DATABASE_PATH': self.temp.name + '/visits.db'})
        self.env.start()
        db.initialize()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_draft_repair_submission_and_register_refresh(self):
        s = db.create_call_session('en-IN', '4821')
        with TestClient(app) as client:
            rows = client.get('/api/register/sessions').json()
            self.assertEqual(rows[0]['record_status'], 'needs_review')
            for field, text in [('visit_done', '1'), ('patient_name', 'Amina'), ('age', '26'),
                                ('symptoms', 'Nausea'), ('followup_needed', '1'),
                                ('followup_date', '2099-08-24'), ('notes', '')]:
                response = client.post(f"/api/register/sessions/{s['id']}/answer", json={'field': field, 'text': text})
                self.assertEqual(response.status_code, 200, response.text)
            for _ in range(2):
                self.assertEqual(client.post(f"/api/calls/{s['id']}/finalize").status_code, 200)
            self.assertEqual(client.get('/api/register/sessions').json(), [])
            visits = client.get('/api/visits').json()
            self.assertEqual(len(visits), 1)
            self.assertEqual(visits[0]['visit']['follow_up_date'], '2099-08-24')

    def test_active_call_cannot_be_repaired(self):
        s = db.create_call_session('en-IN', '4821')
        db.start_phone_call('test')
        db.link_phone_call('test', s['id'])
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/register/sessions').json()[0]['record_status'], 'in_progress')
            self.assertEqual(client.post(f"/api/register/sessions/{s['id']}/answer", json={'field':'visit_done','text':'1'}).status_code, 409)
            db.end_phone_call('test')
            self.assertEqual(client.get('/api/register/sessions').json()[0]['record_status'], 'needs_review')

    def test_date_keypad_and_review_navigation(self):
        async def scenario():
            speech = AsyncMock()
            phone = PhoneConversation(speech)
            for digit in '4148212111':
                await phone.digit(digit)
            await phone.digit('4')
            for digit in '24082099':
                await phone.digit(digit)
            self.assertEqual(phone.stage, 'CONFIRM')
            self.assertIn('24 August 2099', speech.call_args.args[0])
            await phone.digit('1')
            await phone.digit('9')  # Optional notes
            await phone.digit('1')  # Field review
            await phone.digit('1')  # Next field, no instructions
            self.assertNotIn('Press', speech.call_args.args[0])
            before = phone.review_index
            await phone.digit('3')
            self.assertEqual(phone.review_index, before)
            await phone.idle()
            self.assertIn('Press 1 for next', speech.call_args.args[0])
            await phone.digit('9')
            self.assertEqual(phone.stage, 'SUBMIT')
            await phone.digit('9')
            self.assertEqual(db.get_call_session(phone.session['session_id'])['status'], 'draft')
            self.assertEqual(db.list_visits(), [])
        asyncio.run(scenario())

    def test_invalid_keypad_date_stays_in_entry(self):
        async def scenario():
            phone = PhoneConversation(AsyncMock())
            for digit in '41482121114' + '31022099':
                await phone.digit(digit)
            self.assertEqual(phone.stage, 'DATE_KEYPAD')
            self.assertEqual(phone.date_digits, '')
        asyncio.run(scenario())

    def test_review_can_correct_visit_outcome_and_collect_missing_patient(self):
        async def scenario():
            from app.main import answer_call, call_action
            from app.schemas import CallAnswerRequest, CallActionRequest
            phone = PhoneConversation(AsyncMock())
            for digit in '41482121114' + '24082099':
                await phone.digit(digit)
            await phone.digit('1')
            await phone.digit('9')
            await phone.digit('1')  # Review visit outcome.
            await phone.digit('2')  # Edit it.
            await phone.digit('1')  # Visit was completed.
            await phone.digit('1')  # Confirm.
            self.assertEqual(phone.session['state'], 'patient_name')
            sid = phone.session['session_id']
            with self.assertRaises(ValueError):
                db.finalize_call(sid)
            for field, text in [('patient_name', 'Demo patient'), ('age', '26'),
                                ('symptoms', 'Nausea'), ('followup_needed', '2')]:
                await answer_call(sid, CallAnswerRequest(answer_id=field, question_id=field, text=text))
                phone.session = await call_action(sid, CallActionRequest(action='confirm'))
            await phone.ask()
            self.assertEqual(phone.stage, 'FIELD_REVIEW')
            self.assertIn('patient_name', phone.review_fields)
            self.assertNotIn('not_done_reason', phone.review_fields)
            self.assertNotIn('followup_date', phone.review_fields)
            result = db.finalize_call(sid)
            self.assertEqual(result['visit']['visit']['patient_name'], 'Demo patient')
            self.assertEqual(result['visit']['visit']['visit_status'], 'completed')
        asyncio.run(scenario())

    def test_missing_required_date_is_asked_before_review(self):
        async def scenario():
            phone = PhoneConversation(AsyncMock())
            for digit in '4148212111':
                await phone.digit(digit)
            await phone.digit('9')  # Leave date unresolved.
            await phone.digit('9')  # Skip notes.
            self.assertEqual(phone.stage, 'ANSWER')
            self.assertEqual(phone.session['state'], 'followup_date')
            self.assertFalse(phone.done)
        asyncio.run(scenario())
