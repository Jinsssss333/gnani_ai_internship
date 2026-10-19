import asyncio
import json
import os
import re

import httpx

from app.schemas import VisitFields


SYSTEM_PROMPT = (
    "You extract structured facts for one patient's ASHA home visit from a noisy, "
    "possibly code-mixed transcript. Ignore filler, greetings, repetition, "
    "background conversation, unrelated chitchat, and remarks about other people. "
    "Extract only the visit subject's patient_name (when explicitly stated), age, "
    "blood pressure, temperature, symptoms, and explicit follow-up request. "
    "For each field, use the latest clearly stated correction for that same field "
    "(for example, 'BP 120/80—sorry, 110/70' means 110/70). Do not mistake a later "
    "number for a correction if it belongs to another field. If conflicting values "
    "cannot be resolved confidently, return null for that field instead of guessing. "
    "Preserve symptom qualifiers and respect negation: 'no fever' is not a symptom. "
    "Do not diagnose, infer urgency, add unstated facts, or convert units. Set "
    "temperature_f only when Fahrenheit is explicit; otherwise leave it null. "
    "Preserve relative or ambiguous follow-up wording in follow_up_phrase and leave "
    "follow_up_date null unless the date is explicit and unambiguous. Set notes to "
    "null; unrelated conversation does not belong in the register. Return exactly "
    "one valid JSON object with patient_name (string or null), age (integer or null), "
    "vitals (blood_pressure string or null, temperature_f number or null), symptoms "
    "(array), follow_up_date (ISO date or null), follow_up_phrase (string or null), "
    "and notes (null). Do not include markdown or commentary. A worker reviews every "
    "field before saving."
)


def _latest_labeled_value(text: str, label_pattern: str, value_pattern: str) -> str | None:
    """Get the latest labeled value, including an immediate spoken correction."""
    correction = r"sorry|actually|no(?:\s+wait)?|wait|correction|i mean|make that|make it|rather"
    pattern = re.compile(
        rf"\b(?:{label_pattern})\b\s*(?:(?:is|of|was|on|for)\s*)?"
        rf"(?P<value>{value_pattern})"
        rf"(?:(?:\s*[,;]\s*|\s*[-\u2013\u2014]\s*|\s+)(?:{correction})\s*[,;]?\s*"
        rf"(?:(?:it is|it was|it's)\s*)?(?P<corrected>{value_pattern}))*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    latest = matches[-1]
    return latest.group("corrected") or latest.group("value")


def _latest_value(text: str, patterns: list[str]) -> str | None:
    """Return the final non-empty capture among equivalent field patterns."""
    values = []
    for pattern in patterns:
        values.extend(match.group(1) for match in re.finditer(pattern, text, re.IGNORECASE))
    return values[-1].strip() if values else None


def _is_negated(text: str, start: int, end: int) -> bool:
    """Recognize common English, Hindi, and Tamil negations around a symptom."""
    clause_start = max(text.rfind(mark, 0, start) for mark in (",", ".", ";", "।"))
    before = text[clause_start + 1 : start]
    after = text[end : end + 24]
    negation = r"no|not|without|denies?|denied|does not have|doesn't have|nahi|nahin|illa|illai|नहीं|नही|இல்லை|இல்ல"
    return bool(
        re.search(rf"\b(?:{negation})\b", before, re.IGNORECASE)
        or re.match(rf"\s*(?:is\s+)?(?:{negation})\b", after, re.IGNORECASE)
    )


def _demo_extract(transcript: str) -> VisitFields:
    """Field-pattern fallback when Evon is unavailable; it is intentionally not a model."""
    text = transcript.strip()
    lower = text.lower()
    age_value = _latest_value(
        text,
        [
            r"\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|year old|saal|varsh|vayasu)\b",
            r"(?:age|umr|umar|उम्र|आयु|வயது)\s*(?:is|है|:)?\s*(\d{1,3})\b",
        ],
    )
    bp_value = _latest_labeled_value(
        lower,
        r"bp|b\.?p\.?|blood pressure|pressure|ब्लड प्रेशर|रक्तचाप|raktchaap",
        r"\d{2,3}\s*(?:/|by|over|slash)\s*\d{2,3}",
    )
    temperature = _latest_labeled_value(
        lower,
        r"temperature|temp|body temp|body temperature|तापमान|बुखार का ताप|kaichal",
        r"\d{2,3}(?:\.\d+)?(?!\s*(?:celsius|degrees?\s*c|°c)\b)(?:\s*(?:fahrenheit|degrees?\s*f|°?f))?",
    )
    if not temperature:
        temperature = _latest_value(
            lower,
            [
                r"\b(\d{2,3}(?:\.\d+)?)\s*(?:fahrenheit|degrees?\s*f|°?f)\s*"
                r"(?:temperature|temp|तापमान|kaichal)",
            ],
        )
    temperature_number = re.match(r"\d{2,3}(?:\.\d+)?", temperature) if temperature else None

    name = None
    name_match = re.search(
        r"(?:patient(?: name)?|name|for|मरीज(?:\s+का)?\s+नाम|नाम)\s*(?:is|है|:)?\s*([^\s,.;:]+)",
        text,
        re.IGNORECASE,
    )
    if name_match:
        name = name_match.group(1)
    elif text:
        first = re.match(r"([^\s\d,.;:]+)", text)
        if first and first.group(1).lower() not in {
            "patient", "blood", "temperature", "follow", "मरीज", "नाम", "उम्र",
        }:
            name = first.group(1)

    symptom_patterns = [
        ("fever", r"\bfever\b|\bbukhar\b|बुखार|ज्वर|\bkaichal\b"),
        ("nausea", r"\bnausea\b|\bmatli\b|मतली|மயக்கம்"),
        ("cough", r"\bcough\b|\bkhansi\b|खांसी|இருமல்|\birumal\b"),
        ("headache", r"\bheadache\b|\bsar dard\b|सिर दर्द|தலைவலி|\bthalavali\b"),
        ("vomiting", r"\bvomiting\b|\bvomit\b|\bulti\b|उल्टी|வாந்தி"),
        ("dizziness", r"\bdizziness\b|\bchakkar\b|चक्कर|தலைசுற்றல்"),
        ("weakness", r"\bweakness\b|\bkamzori\b|कमजोरी|பலவீனம்"),
        ("pain", r"\bpain\b|\bdard\b|दर्द|வலி"),
        ("fatigue", r"\bfatigue\b|\btiredness\b|थकान|சோர்வு"),
        ("rash", r"\brash\b|चकत्ते|தடிப்பு"),
    ]
    symptoms = []
    for symptom, pattern in symptom_patterns:
        mentions = list(re.finditer(pattern, text, re.IGNORECASE))
        if mentions and not _is_negated(text, mentions[-1].start(), mentions[-1].end()):
            symptoms.append(symptom)

    follow_label = r"follow[ -]?up|review|फॉलो\s*अप|फॉलोअप|अगली\s+मुलाकात|पुनः\s*जांच"
    weekdays = (
        r"today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"aaj|kal|somvaar|mangalvaar|budhvaar|guruvaar|shukravaar|shanivaar|ravivaar|"
        r"आज|कल|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|"
        r"naalai|thingal|sevvai|budhan|viyazhan|velli|sani|nyayiru"
    )
    follow_phrase = _latest_labeled_value(lower, follow_label, weekdays)
    mixed_date_match = re.search(
        rf"(?:{follow_label}).{{0,40}}?({weekdays})|"
        rf"({weekdays}).{{0,40}}?(?:{follow_label})",
        lower,
        re.IGNORECASE,
    )
    phrase = (
        follow_phrase
        if follow_phrase
        else next(value for value in mixed_date_match.groups() if value)
        if mixed_date_match
        else None
    )

    return VisitFields(
        patient_name=name,
        age=int(age_value) if age_value else None,
        vitals={
            "blood_pressure": re.sub(r"\s*(?:/|by|over)\s*", "/", bp_value) if bp_value else None,
            "temperature_f": float(temperature_number.group()) if temperature_number else None,
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


async def _extract_with_gemini(transcript: str, language: str) -> tuple[VisitFields, str]:
    """Use Gemini structured output while keeping the API key on the backend."""
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Gemini is configured but its package is missing. Run: python -m pip install -r requirements.txt"
        ) from exc

    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
    api_key = os.environ["GEMINI_API_KEY"].strip()

    def generate() -> str:
        client = genai.Client(api_key=api_key)
        interaction = client.interactions.create(
            model=model,
            input=(
                f"{SYSTEM_PROMPT}\n\nLanguage: {language}\n"
                f"Transcript: {transcript}"
            ),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": VisitFields.model_json_schema(),
            },
        )
        return interaction.output_text

    try:
        content = await asyncio.to_thread(generate)
        return VisitFields.model_validate_json(content), "gemini"
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not read Gemini's structured response: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini extraction failed: {exc}") from exc


async def extract(transcript: str, language: str) -> tuple[VisitFields, str]:
    if os.getenv("GEMINI_API_KEY", "").strip():
        return await _extract_with_gemini(transcript, language)

    endpoint = (
        os.getenv("EVON_CHAT_COMPLETIONS_URL")
        or os.getenv("EVON_INFERENCE_ENDPOINT", "")
    ).strip()
    if not endpoint:
        return _demo_extract(transcript), "demo-parser"

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("EVON_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": os.getenv("EVON_MODEL") or os.getenv("EVON_MODEL_NAME", "gnani-evon-v3.3"),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Language: {language}\nTranscript: {transcript}"},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            # Some OpenAI-compatible servers do not implement response_format.
            # The prompt still requires a JSON object, so retry once without it.
            if response.status_code in {400, 422}:
                compatibility_payload = {
                    key: value for key, value in payload.items() if key != "response_format"
                }
                response = await client.post(
                    endpoint, json=compatibility_payload, headers=headers
                )
            response.raise_for_status()
            result = response.json()
    except httpx.RequestError:
        # A field worker should still be able to review a transcription when the
        # optional model server is down or unreachable. The returned source makes
        # the fallback explicit in the UI and persisted record.
        return _demo_extract(transcript), "demo-parser"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            return _demo_extract(transcript), "demo-parser"
        raise

    try:
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content)
        fields = VisitFields.model_validate(_extract_json(content))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Could not read Evon's response: {exc}") from exc
    return fields, "evon-v3.3"
