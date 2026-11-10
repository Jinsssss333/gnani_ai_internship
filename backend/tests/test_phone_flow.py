import asyncio
import base64
import io
import os
import tempfile
import unittest
import wave
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import db
from app.main import app
from app.phone_gateway import app as gateway
from app.phone_flow import PhoneConversation
from app.telephony import authorized, wav_to_pcm


class PhoneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATABASE_PATH": self.directory.name + "/visits.db",
            "AUDIO_STORAGE_PATH": self.directory.name + "/audio", "TTS_CACHE_PATH": self.directory.name + "/tts"})
        self.env.start()
        db.initialize()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_full_phone_visit_with_final_correction_and_duplicate_save(self):
        async def scenario():
            speech = AsyncMock()
            phone = PhoneConversation(speech)
            await phone.welcome()
            for digit in "414821":
                await phone.digit(digit)
            self.assertEqual(phone.session["state"], "visit_done")
            await phone.digit("1")
            await phone.digit("1")

            async def answer(transcript, value):
                phone.add_audio(b"\0\0" * 8000)
                with patch("app.phone_flow.prisma.transcribe", AsyncMock(return_value=transcript)), patch(
                    "app.phone_flow.extract_field", AsyncMock(return_value=(value, transcript))):
                    await phone.digit("1")
                self.assertEqual(phone.stage, "CONFIRM")
                await phone.digit("1")

            await answer("Amina", "Amina")
            await answer("26 years", 26)
            await answer("Mild fever. No cough.", {"reported": ["mild fever"], "negated": ["cough"]})
            await phone.digit("1")
            await phone.digit("1")
            await answer("Friday", {"phrase": "Friday", "date": "2026-11-13"})
            await phone.digit("9")
            self.assertEqual(phone.stage, "REVIEW")
            await phone.digit("2")
            await phone.digit("4")
            await answer("Monday", {"phrase": "Monday", "date": "2026-11-16"})
            self.assertEqual(phone.stage, "REVIEW")
            await phone.digit("3")
            self.assertTrue(phone.done)
            saved = db.finalize_call(phone.session["session_id"])
            self.assertEqual(len(db.list_visits()), 1)
            self.assertEqual(len(db.list_audit_events()), 1)
            visit = saved["visit"]["visit"]
            self.assertEqual(visit["follow_up_date"], "2026-11-16")
            self.assertEqual(visit["evidence"]["followup_date"]["previous_attempts"][0]["value"]["phrase"], "Friday")
            self.assertEqual(visit["negated_symptoms"], ["cough"])
            self.assertIn("Monday", saved["visit"]["transcript"])
        asyncio.run(scenario())

    def test_finalize_cannot_bypass_missing_required_answers(self):
        session = db.create_call_session("en-IN", "4821")
        session["current_question_id"] = "FINAL_REVIEW"
        db.update_call_session(session)
        with self.assertRaises(ValueError):
            db.finalize_call(session["id"])
        self.assertEqual(db.list_visits(), [])

    def test_not_completed_visit_does_not_ask_patient_fields(self):
        async def scenario():
            phone = PhoneConversation(AsyncMock())
            for digit in "4148212111":
                await phone.digit(digit)
            self.assertEqual(phone.session["state"], "followup_date")
            self.assertNotIn("patient_name", phone.session["answers"])
        asyncio.run(scenario())

    def test_audio_cap_and_wire_format(self):
        phone = PhoneConversation(AsyncMock())
        phone.listening = True
        self.assertTrue(phone.add_audio(b"\0" * 900000))
        self.assertEqual(len(phone.audio), 16000 * 2 * 25)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * 4800)
        self.assertEqual(len(wav_to_pcm(output.getvalue(), 16000)), 3200)

    def test_unauthorized_socket_rejected(self):
        with patch.dict(os.environ, {"TELEPHONY_USER": "", "TELEPHONY_PASSWORD": ""}):
            self.assertFalse(authorized(""))
            with TestClient(app) as client:
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("/api/telephony/exotel"):
                        pass

    def test_public_gateway_excludes_supervisor_and_write_apis(self):
        with TestClient(gateway) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            for path in ("/api/visits", "/api/audit", "/api/telephony/calls", "/docs", "/openapi.json"):
                self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.post("/api/visits", json={}).status_code, 404)

    def test_exotel_handshake_audio_and_keypad(self):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            # A short final frame still needs padding to Exotel's minimum size.
            wav.writeframes(b"\0\0" * 1761)
        # Speech is mocked; the cache is isolated in the temporary test directory.
        with patch.dict(os.environ, {"TELEPHONY_USER": "demo", "TELEPHONY_PASSWORD": "test-only", "EXOTEL_ACCOUNT_SID": "test-account"}), patch(
            "app.telephony.timbre.synthesize", AsyncMock(return_value=(output.getvalue(), "audio/wav"))):
            headers = {"Authorization": "Basic " + base64.b64encode(b"demo:test-only").decode()}
            with TestClient(gateway) as client:
                with client.websocket_connect("/api/telephony/exotel", headers=headers) as ws:
                    ws.send_json({"event": "start", "start": {"account_sid": "test-account", "call_sid": "call-test", "stream_sid": "stream-1", "media_format": {"encoding": "audio/x-raw", "sample_rate": "16000", "bit_rate": "16"}}})
                    def listen():
                        heard = False
                        while True:
                            message = ws.receive_json()
                            if message["event"] == "media":
                                frame = base64.b64decode(message["media"]["payload"])
                                self.assertGreaterEqual(len(frame), 3200)
                                self.assertEqual(len(frame) % 320, 0)
                                heard = True
                            if message["event"] == "mark":
                                ws.send_json(message)
                                break
                        self.assertTrue(heard)
                    listen()
                    listen()
                    ws.send_json({"event": "dtmf", "sequence_number": "1", "dtmf": {"digit": "4"}})
                    listen()
                    ws.send_json({"event": "stop"})


if __name__ == "__main__":
    unittest.main()
