import os

import httpx


async def transcribe(audio: bytes, filename: str, content_type: str, language: str) -> str:
    endpoint = os.getenv("PRISMA_API_URL", "").strip()
    key_id = os.getenv("PRISMA_API_KEY_ID", "").strip()
    if not endpoint or not key_id:
        raise RuntimeError(
            "Prisma is not configured yet. Add PRISMA_API_URL and PRISMA_API_KEY_ID to backend/.env."
        )

    language_field = os.getenv("PRISMA_LANGUAGE_FIELD", "language_code")
    headers = {"X-API-Key-ID": key_id}
    data = {
        language_field: language,
        "preferred_language": language,
        "format": "transcribe",
        "itn_native_numerals": "true",
    }
    files = {"audio_file": (filename, audio, content_type or "audio/webm")}

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(endpoint, data=data, files=files, headers=headers)
        response.raise_for_status()
        payload = response.json()

    transcript = payload.get("transcript") or payload.get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise RuntimeError("Prisma returned a response without a transcript.")
    return transcript.strip()
