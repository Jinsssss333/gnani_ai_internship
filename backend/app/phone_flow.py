"""Telephone keypad workflow, independent of Exotel's wire protocol."""
import asyncio
import io
import os
import wave
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app import db
from app.phone_fields import extract_field
from app.phone_prompts import LANGUAGE_MENU, PROMPTS
from app.providers import prisma
from app.questions import question
from app.schemas import CallActionRequest, CallAnswerRequest, CallStartRequest


class PhoneConversation:
    def __init__(self, speak, sample_rate=16000, call_sid=None):
        self.speak = speak
        self.sample_rate = sample_rate
        self.call_sid = call_sid
        self.language = "en-IN"
        self.stage = "LANGUAGE"
        self.session = None
        self.code = ""
        self.audio = bytearray()
        self.listening = False
        self.done = False
        self.editable = []
        self.failures = 0

    @property
    def messages(self):
        return PROMPTS[self.language]

    async def say(self, text):
        self.listening = False
        await self.speak(text, self.language)

    async def welcome(self):
        for language, text in LANGUAGE_MENU:
            await self.speak(text, language)

    def add_audio(self, pcm):
        if not self.listening or len(pcm) % 2:
            return False
        limit = self.sample_rate * 2 * 25
        self.audio.extend(pcm[:max(0, limit - len(self.audio))])
        return len(self.audio) >= limit

    def value_text(self, answer):
        value = answer.get("value")
        if value is None:
            return self.messages["none"]
        if isinstance(value, bool):
            return self.messages["yes" if value else "no"]
        if isinstance(value, dict):
            if "date" in value:
                return f"{value['phrase']}. {value['date']}"
            # Confirm the actual structured fields that will be saved, not background chatter.
            parts = []
            for key in ("reported", "negated"):
                if value.get(key):
                    parts.append(f"{self.messages[key]}: {', '.join(value[key])}")
            return ". ".join(parts)
        return str(value).replace("_", " ")

    async def ask(self):
        state = self.session["state"]
        self.audio.clear()
        if state == "FINAL_REVIEW":
            self.stage = "REVIEW"
            await self.say(self.messages["review"])
            return
        self.stage = "ANSWER"
        item = question(state)
        text = self.messages[state]
        if item["type"] not in {"boolean", "enum"}:
            text += " " + self.messages["record"]
        if item.get("optional"):
            text += " " + self.messages["optional"]
        await self.say(text)
        self.listening = item["type"] not in {"boolean", "enum"}

    async def readback(self):
        self.stage = "CONFIRM"
        answer = self.session["answers"][self.session["state"]]
        await self.say(f"{self.messages['heard']}: {self.value_text(answer)}. {self.messages['confirm']}")

    async def finish_audio(self):
        from app.main import _session_response
        if len(self.audio) < self.sample_rate // 5:
            await self.say(self.messages["invalid"])
            await self.ask()
            return
        self.listening = False
        session_id = self.session["session_id"]
        self.stage = "PROCESSING"
        field = self.session["state"]
        answer_id = str(uuid4())
        root = Path(os.getenv("AUDIO_STORAGE_PATH", str(Path(__file__).resolve().parents[1] / "storage" / "audio")))
        directory = root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, self.sample_rate, 0, "NONE", "not compressed"))
            wav.writeframes(bytes(self.audio))
        data = output.getvalue()
        (directory / f"{answer_id}.wav").write_bytes(data)
        try:
            transcript = await asyncio.wait_for(prisma.transcribe(data, "answer.wav", "audio/wav", self.language), 25)
            today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
            value, evidence = await extract_field(field, transcript, self.language, today)
            session = db.get_call_session(session_id)
            if session["current_question_id"] != field:
                raise ValueError("Question changed.")
            prior = session["answers"].get(field)
            history = [] if not prior else [*prior.get("previous_attempts", []),
                {k: v for k, v in prior.items() if k != "previous_attempts"}]
            session["answers"][field] = {
                "answer_id": answer_id, "question_id": field, "attempt": len(history) + 1,
                "transcript": transcript, "value": value, "evidence_quote": evidence,
                "extraction_source": "gemini", "transcription_source": "prisma",
                "audio_ref": f"{session_id}/{answer_id}.wav", "confirmed": False,
                "needs_confirmation": True, "previous_attempts": history,
            }
            db.update_call_session(session)
            self.session = _session_response(session)
            self.failures = 0
            await self.readback()
        except (ValueError, RuntimeError, TimeoutError, KeyError, IndexError, httpx.HTTPError):
            self.failures += 1
            await self.say(self.messages["failed"])
            if self.failures >= 3:
                self.done = True
                await self.say(self.messages["unavailable"])
            else:
                await self.ask()

    async def digit(self, digit):
        from app.main import start_call, answer_call, call_action, finalize_call
        from fastapi import HTTPException

        if self.stage == "LANGUAGE":
            if digit not in {"2", "4"}:
                await self.welcome()
                return
            self.language = {"2": "hi-IN", "4": "en-IN"}[digit]
            self.stage = "FORM"
            await self.say(self.messages["form"])
        elif self.stage == "FORM":
            if digit == "1":
                self.stage = "CODE"
                await self.say(self.messages["code"])
            else:
                await self.say(self.messages["form"])
        elif self.stage == "CODE":
            if digit.isdigit():
                self.code += digit
            if len(self.code) == 4:
                code, self.code = self.code, ""
                try:
                    self.session = await start_call(CallStartRequest(language_code=self.language, visit_code=code))
                    if self.call_sid:
                        db.link_phone_call(self.call_sid, self.session["session_id"])
                    await self.ask()
                except HTTPException:
                    await self.say(self.messages["invalid"] + " " + self.messages["code"])
        elif self.stage == "ANSWER":
            item = question(self.session["state"])
            if digit == "9" and item.get("optional"):
                self.session = await call_action(self.session["session_id"], CallActionRequest(action="skip"))
                await self.ask()
            elif item["type"] in {"boolean", "enum"}:
                if digit not in (item.get("keypad") or item.get("options")):
                    await self.ask()
                    return
                self.session = await answer_call(self.session["session_id"], CallAnswerRequest(
                    answer_id=str(uuid4()), question_id=item["id"], dtmf=digit))
                await self.readback()
            elif digit == "1":
                await self.finish_audio()
            elif digit == "2":
                await self.ask()
        elif self.stage == "CONFIRM":
            if digit == "1":
                self.session = await call_action(self.session["session_id"], CallActionRequest(action="confirm"))
                await self.ask()
            elif digit == "2":
                self.session = await call_action(self.session["session_id"], CallActionRequest(action="correct"))
                await self.ask()
            else:
                await self.readback()
        elif self.stage == "REVIEW":
            if digit == "1":
                for field, answer in self.session["answers"].items():
                    await self.say(self.messages[field] + " " + self.value_text(answer))
                await self.say(self.messages["review"])
            elif digit == "2":
                self.editable = [f for f in self.session["answers"] if f in {"patient_name", "age", "symptoms", "followup_date", "notes"}]
                self.stage = "EDIT"
                await self.say(self.messages["edit"])
                for i, field in enumerate(self.editable, 1):
                    await self.say(f"{i}. {self.messages[field]}")
            elif digit == "3":
                await finalize_call(self.session["session_id"])
                self.done = True
                await self.say(self.messages["saved"])
            else:
                await self.say(self.messages["review"])
        elif self.stage == "EDIT":
            if digit.isdigit() and 1 <= int(digit) <= len(self.editable):
                field = self.editable[int(digit) - 1]
                self.session = await call_action(self.session["session_id"], CallActionRequest(action="correct", field=field))
                await self.ask()
            else:
                await self.say(self.messages["edit"])
