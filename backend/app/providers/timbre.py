import base64
import os

import httpx


async def synthesize(text: str, language: str) -> tuple[bytes, str]:
    endpoint = os.getenv("TIMBRE_API_URL", "").strip()
    api_key = os.getenv("TIMBRE_API_KEY", "").strip()
    if not endpoint or not api_key:
        raise RuntimeError(
            "Timbre is not configured yet. Add TIMBRE_API_URL and TIMBRE_API_KEY to backend/.env."
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": os.getenv("TIMBRE_MODEL", "timbre-2.5"),
        "language": language or os.getenv("TIMBRE_LANGUAGE", "hi-IN"),
        "voice": os.getenv("TIMBRE_VOICE", "Nalini"),
        "sample_rate": 24000,
        "text": text,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0]
        if "json" in content_type:
            result = response.json()
            encoded = result.get("audio_base64") or result.get("audio")
            if not isinstance(encoded, str):
                raise RuntimeError("Timbre returned JSON without audio data.")
            return base64.b64decode(encoded), result.get("content_type", "audio/wav")
        return response.content, content_type
