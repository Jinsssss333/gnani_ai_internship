import os

import httpx


async def transcribe(audio: bytes, filename: str, content_type: str, language: str) -> str:
    stt_base_url = os.getenv("GNANI_STT_BASE_URL", "https://api.vachana.ai").rstrip("/")
    endpoint = os.getenv("PRISMA_API_URL", f"{stt_base_url}/stt/v3").strip()
    key_id = (os.getenv("PRISMA_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID", "")).strip()
    if not endpoint or not key_id:
        raise RuntimeError(
            "Prisma is not configured yet. Add PRISMA_API_URL and PRISMA_API_KEY_ID to backend/.env."
        )

    headers = {"X-API-Key-ID": key_id}
    data = {
        "language_code": language,
        "format": os.getenv("PRISMA_FORMAT", "transcribe"),
        "itn_native_numerals": os.getenv("PRISMA_ITN_NATIVE_NUMERALS", "false"),
    }
    files = {"audio_file": (filename, audio, content_type or "audio/wav")}

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(endpoint, data=data, files=files, headers=headers)
        response.raise_for_status()
        payload = response.json()

    transcript = payload.get("transcript") or payload.get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise RuntimeError("Prisma returned a response without a transcript.")
    return transcript.strip()
