import json
import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx

from app.phone_fields import extract_field
from app.phone_flow import PhoneConversation


class FieldTests(unittest.IsolatedAsyncioTestCase):
    async def extract(self, field="age", transcript="26 years", envelope=None, **changes):
        data = dict(text="", age=26, reported=[], negated=[], weekday=None,
                    days_ahead=None, iso_date=None, evidence=transcript, clear=True)
        data.update(changes)
        payload = envelope if envelope is not None else {
            "candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        client = httpx.AsyncClient(transport=transport)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only"}), patch(
                "app.phone_fields.httpx.AsyncClient", return_value=client):
            return await extract_field(field, transcript, "en-IN", date(2026, 11, 10))

    async def test_latest_corrected_value_and_exact_evidence(self):
        value, quote = await self.extract(transcript="Age 25, sorry 26 years", evidence="26 years")
        self.assertEqual((value, quote), (26, "26 years"))

    async def test_bad_shapes_and_missing_candidates_are_retryable(self):
        for changes in ({"age": True}, {"age": "26"}, {"clear": "true"},
                        {"reported": "fever"}, {"text": None}, {"evidence": "invented"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                await self.extract(**changes)
        for payload in ({}, {"candidates": []}, {"candidates": None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                await self.extract(envelope=payload)

    async def test_symptom_negation_and_structured_readback(self):
        value, _ = await self.extract(field="symptoms", transcript="Tea please. Fever, no cough.",
                                      age=None, reported=["fever"], negated=["cough"])
        phone = PhoneConversation(AsyncMock())
        spoken = phone.value_text({"value": value, "transcript": "Tea please. Fever, no cough."})
        self.assertEqual(spoken, "Symptoms present: fever. Symptoms absent: cough")
        for changes in ({"reported": [], "negated": []}, {"reported": [""]}, {"negated": [None]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                await self.extract(field="symptoms", **changes)

    async def test_dates_use_reference_day_and_reject_conflicts(self):
        value, _ = await self.extract(field="followup_date", transcript="Friday", age=None,
                                      text="Friday", weekday=4)
        self.assertEqual(value["date"], "2026-11-13")
        for changes in ({"weekday": 4, "days_ahead": 3}, {"iso_date": "2020-01-01"},
                        {"iso_date": "tomorrow"}, {"days_ahead": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                await self.extract(field="followup_date", text="Friday", **changes)
