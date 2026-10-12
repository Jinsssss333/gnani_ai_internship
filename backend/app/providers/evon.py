import json
import os
import re

import httpx

from app.schemas import VisitFields


SYSTEM_PROMPT = (
    "You extract facts explicitly stated in an ASHA home-visit note. "
    "Return only one JSON object with fields patient_name (string or null), "
    "age (integer or null), vitals (object with blood_pressure string or null "
    "and temperature_f number or null), symptoms (array of strings), "
    "follow_up_date (ISO YYYY-MM-DD or null), follow_up_phrase (original "
    "relative date phrase or null), and notes (string or null). Do not diagnose, "
    "infer urgency, invent missing values, or change units. If a date is relative "
    "or ambiguous, preserve its wording in follow_up_phrase and leave "
    "follow_up_date null. The worker reviews every field before saving."
)


def _demo_extract(transcript: str) -> VisitFields:
    """Transparent fallback for UI development when Evon is not configured."""
    text = transcript.strip()
    lower = text.lower()
    age_match = re.search(r"\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|year old)\b", lower)
    bp_match = re.search(r"\b(?:bp|blood pressure)\s*(?:is|of)?\s*(\d{2,3}\s*/\s*\d{2,3})\b", lower)
    temp_match = re.search(r"\b(?:temperature|temp)\s*(?:is|of)?\s*(\d{2,3}(?:\.\d+)?)\b", lower)
    follow_match = re.search(
        r"\b(?:follow[ -]?up|review)\s*(?:on|for)?\s*(?:set|scheduled)?\s*([a-z]+(?:\s+\d{1,2})?)\b",
        lower,
    )

    name = None
    name_match = re.search(r"\b(?:patient|name|for)\s*[: ]\s*([A-Z][a-z]+)\b", text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
    elif text:
        first = re.match(r"([A-Z][a-z]{1,24})\b", text)
        if first and first.group(1).lower() not in {"patient", "blood", "temperature", "follow"}:
            name = first.group(1)

    symptom_words = [
        "fever", "nausea", "cough", "headache", "vomiting", "dizziness",
        "weakness", "pain", "fatigue", "rash",
    ]
    symptoms = [word for word in symptom_words if word in lower]
    phrase = follow_match.group(1).strip() if follow_match else None

    return VisitFields(
        patient_name=name,
        age=int(age_match.group(1)) if age_match else None,
        vitals={
            "blood_pressure": re.sub(r"\s+", "", bp_match.group(1)) if bp_match else None,
            "temperature_f": float(temp_match.group(1)) if temp_match else None,
        },
        symptoms=symptoms,
        follow_up_phrase=phrase,
        notes=None,
    )


def _extract_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise RuntimeError("Evon returned text that was not valid JSON.")


async def extract(transcript: str, language: str) -> tuple[VisitFields, str]:
    endpoint = os.getenv("EVON_CHAT_COMPLETIONS_URL", "").strip()
    if not endpoint:
        return _demo_extract(transcript), "demo-parser"

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("EVON_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": os.getenv("EVON_MODEL", "evon-v3.3"),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Language: {language}\nTranscript: {transcript}"},
        ],
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()

    try:
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content)
        fields = VisitFields.model_validate(_extract_json(content))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not read Evon's response: {exc}") from exc
    return fields, "evon-v3.3"
