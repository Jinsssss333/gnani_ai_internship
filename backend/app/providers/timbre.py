import os

import httpx


async def synthesize(text: str, language: str) -> tuple[bytes, str]:
    endpoint = os.getenv("TIMBRE_API_URL", "https://api.vachana.ai/api/v1/tts/inference").strip()
    api_key = (os.getenv("TIMBRE_API_KEY_ID") or os.getenv("GNANI_API_KEY_ID", "")).strip()
    if not endpoint or not api_key:
        raise RuntimeError(
            "Timbre is not configured yet. Add TIMBRE_API_KEY_ID to backend/.env."
        )

    headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
    payload = {
        "model": os.getenv("TIMBRE_MODEL", "timbre-v2.5"),
        "language": language or os.getenv("TIMBRE_LANGUAGE", "hi-IN"),
        "voice": os.getenv("TIMBRE_VOICE", "Nalini"),
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 48000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
        "text": text,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0]
        return response.content, content_type
