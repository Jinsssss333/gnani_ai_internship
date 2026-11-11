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
from app.call_flow import active_fields, first_unresolved
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
        self.review_index = 0
        self.review_fields = []
        self.review_edit = False
        self.date_digits = ''
        self.idle_count = 0
        self.revision = 0

    async def save_draft(self):
        if self.session:
            session = db.get_call_session(self.session['session_id'])
            session['status'] = 'draft'
            db.update_call_session(session)
        self.done = True
        await self.say(self.messages['unavailable'])

    async def review_field(self):
        if self.review_index >= len(self.review_fields):
            self.stage = 'SUBMIT'
            await self.say(self.messages['submit_menu'])
            return
        self.stage = 'FIELD_REVIEW'
        field = self.review_fields[self.review_index]
        await self.say(self.messages.get('label_' + field, field.replace('_', ' ')) + ': ' + self.value_text(self.session['answers'].get(field, {})))

    async def idle(self):
        self.idle_count += 1
        if self.idle_count >= 3:
            await self.save_draft()
        elif self.stage == 'FIELD_REVIEW':
            await self.say(self.messages['review_keys'])
        elif self.stage == 'SUBMIT':
            await self.say(self.messages['submit_menu'])
        elif self.stage == 'DATE_KEYPAD':
            await self.say(self.messages['date_keypad'])
        elif self.stage == 'CONFIRM':
            await self.say(self.messages['confirm'])
        elif self.stage == 'ANSWER':
            await self.say(self.messages['record'])
            self.listening = question(self.session['state'])['type'] not in {'boolean', 'enum'}
        elif self.stage == 'REVIEW':
            await self.say(self.messages['review'])
        else:
            await self.say(self.messages.get(self.stage.lower(), self.messages['invalid']))

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
                date = datetime.fromisoformat(value['date'])
                months = ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई', 'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर']
                month = months[date.month - 1] if self.language == 'hi-IN' else date.strftime('%B')
                return f'{date.day} {month} {date.year}'
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
        if state == 'FINAL_REVIEW':
            missing = first_unresolved(self.session['answers'])
            if missing != 'FINAL_REVIEW':
                session = db.get_call_session(self.session['session_id'])
                session['current_question_id'] = missing
                db.update_call_session(session)
                from app.main import _session_response
                self.session = _session_response(session)
                await self.say(self.messages['missing_required'])
                await self.ask()
                return
        if state == "FINAL_REVIEW" and self.review_edit:
            self.review_edit = False
            self.review_fields = active_fields(self.session['answers'])
            self.review_index = 0
            await self.review_field()
            return
        if state == "FINAL_REVIEW":
            self.stage = "REVIEW"
            await self.say(self.messages["review"])
            return
        self.stage = "ANSWER"
        item = question(state)
        text = self.messages[state]
        if item["type"] not in {"boolean", "enum"}:
            text += " " + self.messages["record"]
        if state in {'followup_date', 'age'}:
            text += ' ' + self.messages['keypad_option']
        if item.get("optional"):
            text += " " + self.messages["optional"]
        await self.say(text)
        self.listening = item["type"] not in {"boolean", "enum"}

    async def readback(self):
        self.stage = "CONFIRM"
        answer = self.session["answers"][self.session["state"]]
        context = self.messages.get('label_' + self.session['state'], self.messages['heard'])
        explanation = self.messages['not_completed_branch'] if self.session['state'] == 'visit_done' and answer.get('value') is False else ''
        await self.say(f"{context}: {self.value_text(answer)}. {explanation} {self.messages['confirm']}")

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
        transcript = ''
        processing_step = 'transcription'
        try:
            transcript = await asyncio.wait_for(prisma.transcribe(data, "answer.wav", "audio/wav", self.language), 25)
            processing_step = 'extraction'
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
        except (ValueError, RuntimeError, TimeoutError, KeyError, IndexError, httpx.HTTPError):
            # Keep failed attempts recoverable without treating them as accepted values.
            session = db.get_call_session(session_id)
            prior = session['answers'].get(field)
            history = [] if not prior else [*prior.get('previous_attempts', []),
                {k: v for k, v in prior.items() if k != 'previous_attempts'}]
            session['answers'][field] = {
                'answer_id': answer_id, 'question_id': field, 'transcript': transcript,
                'value': None, 'evidence_quote': '', 'confirmed': False,
                'needs_confirmation': True, 'awaiting_replacement': True,
                'failure_stage': processing_step, 'audio_ref': f'{session_id}/{answer_id}.wav',
                'previous_attempts': history,
            }
            db.update_call_session(session)
            self.session = _session_response(session)
            self.failures += 1
            await self.say(self.messages["failed"])
            if field in {'followup_date', 'age'}:
                self.stage = 'DATE_KEYPAD'
                self.date_digits = ''
                await self.say(self.messages['date_keypad' if field == 'followup_date' else 'age_keypad'])
            elif self.failures >= 3:
                await self.save_draft()
            else:
                await self.ask()
            return
        # Playback failure must not overwrite a successfully extracted answer.
        await self.readback()

    async def digit(self, digit):
        from app.main import start_call, answer_call, call_action, finalize_call
        from fastapi import HTTPException

        self.idle_count = 0
        self.revision += 1
        if self.stage == 'DATE_KEYPAD':
            if digit == '*':
                self.date_digits = ''
            elif digit == '#' or (digit.isdigit() and len(self.date_digits + digit) == 8 and self.session['state'] == 'followup_date'):
                if digit != '#':
                    self.date_digits += digit
                try:
                    field = self.session['state']
                    if field == 'followup_date':
                        target = datetime.strptime(self.date_digits, '%d%m%Y').date()
                        if len(self.date_digits) != 8 or target < datetime.now(timezone(timedelta(hours=5, minutes=30))).date():
                            raise ValueError()
                        value = {'date': target.isoformat(), 'phrase': self.date_digits}
                    else:
                        value = int(self.date_digits)
                        if not 0 <= value <= 120:
                            raise ValueError()
                    session = db.get_call_session(self.session['session_id'])
                    previous = session['answers'].get(field)
                    session['answers'][field] = {'answer_id': str(uuid4()), 'question_id': field,
                        'value': value, 'transcript': self.date_digits, 'evidence_quote': self.date_digits,
                        'confirmed': False, 'needs_confirmation': True, 'extraction_source': 'keypad',
                        'previous_attempts': ([*previous.get('previous_attempts', []), {k:v for k,v in previous.items() if k != 'previous_attempts'}] if previous else [])}
                    db.update_call_session(session)
                    from app.main import _session_response
                    self.session = _session_response(session)
                    await self.readback()
                except ValueError:
                    self.date_digits = ''
                    await self.say(self.messages['invalid'] + ' ' + self.messages['date_keypad' if self.session['state'] == 'followup_date' else 'age_keypad'])
            elif digit.isdigit() and len(self.date_digits) < 8:
                self.date_digits += digit
            return
        if self.stage == 'FIELD_REVIEW':
            if digit == '1':
                self.review_index += 1
                await self.review_field()
            elif digit == '2':
                field = self.review_fields[self.review_index]
                if field in active_fields(self.session['answers']):
                    self.session = await call_action(self.session['session_id'], CallActionRequest(action='correct', field=field))
                    self.review_edit = True
                    await self.ask()
                else:
                    await self.say(self.messages['fixed_field'])
            elif digit == '3':
                await self.review_field()
            elif digit == '9':
                self.stage = 'SUBMIT'
                await self.say(self.messages['submit_menu'])
            else:
                await self.say(self.messages['review_keys'])
            return
        if self.stage == 'SUBMIT':
            self.review_fields = active_fields(self.session['answers'])
            if digit == '1':
                try:
                    await finalize_call(self.session['session_id'])
                    self.done = True
                    await self.say(self.messages['saved'])
                except HTTPException:
                    await self.save_draft()
            elif digit == '2':
                self.review_index = 0
                await self.say(self.messages['review_keys'])
                await self.review_field()
            elif digit == '9':
                await self.save_draft()
            else:
                await self.say(self.messages['submit_menu'])
            return
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
            if digit == '4' and self.session['state'] in {'followup_date', 'age'}:
                self.listening = False
                self.stage = 'DATE_KEYPAD'
                self.date_digits = ''
                await self.say(self.messages['date_keypad' if self.session['state'] == 'followup_date' else 'age_keypad'])
            elif digit == '9' and self.session['state'] == 'followup_date':
                session = db.get_call_session(self.session['session_id'])
                session['current_question_id'] = 'notes'
                db.update_call_session(session)
                from app.main import _session_response
                self.session = _session_response(session)
                await self.ask()
            elif digit == '0':
                await self.save_draft()
            elif digit == "9" and item.get("optional"):
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
                self.review_fields = active_fields(self.session['answers'])
                self.review_index = 0
                await self.say(self.messages['review_keys'])
                await self.review_field()
            elif digit == "2":
                self.editable = active_fields(self.session['answers'])
                self.stage = "EDIT"
                await self.say(self.messages["edit"])
                for i, field in enumerate(self.editable, 1):
                    await self.say(f"{i}. {self.messages[field]}")
            elif digit == "3":
                self.stage = 'SUBMIT'
                await self.say(self.messages['submit_menu'])
            elif digit == '9':
                await self.save_draft()
            else:
                await self.say(self.messages["review"])
        elif self.stage == "EDIT":
            if digit.isdigit() and 1 <= int(digit) <= len(self.editable):
                field = self.editable[int(digit) - 1]
                self.session = await call_action(self.session["session_id"], CallActionRequest(action="correct", field=field))
                await self.ask()
            else:
                await self.say(self.messages["edit"])
