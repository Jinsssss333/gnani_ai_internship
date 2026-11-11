import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from app import db
from app.main import start_call, answer_call, call_action
from app.schemas import CallStartRequest, CallAnswerRequest, CallActionRequest


class CorrectionTests(unittest.TestCase):
    def test_replacement_requires_new_answer_and_preserves_original(self):
        async def scenario():
            session = await start_call(CallStartRequest(visit_code="4821"))
            sid = session["session_id"]
            await answer_call(sid, CallAnswerRequest(answer_id="original", question_id="visit_done", dtmf="1"))
            corrected = await call_action(sid, CallActionRequest(action="correct"))
            self.assertTrue(corrected["answers"]["visit_done"]["awaiting_replacement"])
            with self.assertRaises(HTTPException):
                await call_action(sid, CallActionRequest(action="confirm"))
            replaced = await answer_call(sid, CallAnswerRequest(answer_id="replacement", question_id="visit_done", dtmf="2"))
            answer = replaced["answers"]["visit_done"]
            self.assertFalse(answer["confirmed"])
            self.assertTrue(answer["previous_attempts"][0]["value"])
            next_state = await call_action(sid, CallActionRequest(action="confirm"))
            self.assertEqual(next_state["state"], "not_done_reason")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"DATABASE_PATH": directory + "/test.db"}):
                db.initialize()
                asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
