"""Phone-demo preflight. --live spends credits on synthetic provider requests only."""
import argparse
import asyncio
import io
import os
import wave
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.phone_fields import extract_field
from app.providers import prisma, timbre
from app.telephony import wav_to_pcm


def configured(*names):
    return any(os.getenv(name, "").strip() for name in names)


async def live_checks():
    passed = True
    transcript = "The fictional patient is 26 years old."

    async def check(label, operation):
        nonlocal passed
        try:
            result = await asyncio.wait_for(operation(), 75)
            print(f"PASS {label}", flush=True)
            return result
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            hint = " Check model access, quota and billing; no automatic retry." if code == 429 else " Check provider access and configuration."
            print(f"FAIL {label}: HTTP {code}.{hint}", flush=True)
        except Exception as exc:
            # Provider exception bodies may contain credentials or request data.
            print(f"FAIL {label}: {type(exc).__name__}. Check configuration and connectivity.", flush=True)
        passed = False
        return None

    async def speech_roundtrip():
        audio, _ = await timbre.synthesize("यह एक परीक्षण है। मरीज की उम्र छब्बीस साल है।", "hi-IN")
        pcm = wav_to_pcm(audio, 16000)
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            target.writeframes(pcm)
        result = await prisma.transcribe(output.getvalue(), "synthetic-test.wav", "audio/wav", "hi-IN")
        if not result.strip():
            raise ValueError("Empty transcript")
        return result

    recognized = await check("Hindi Timbre -> Prisma", speech_roundtrip)
    if recognized:
        transcript = recognized

    async def extraction():
        value, _ = await extract_field("age", transcript, "hi-IN" if recognized else "en-IN", date.today())
        if value != 26:
            raise ValueError("Synthetic age did not match")

    await check("Gemini extraction (expected age 26)", extraction)

    async def english_prompt():
        audio, _ = await timbre.synthesize("Welcome to SunoCare. For English, press four.", "en-IN")
        wav_to_pcm(audio, 16000)

    await check("English Timbre prompt", english_prompt)
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send synthetic audio/text to Gnani and Gemini; consumes credits")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent / ".env")
    checks = {
        "Prisma key": configured("PRISMA_API_KEY_ID", "GNANI_API_KEY_ID"),
        "Timbre key": configured("TIMBRE_API_KEY_ID", "GNANI_API_KEY_ID"),
        "Gemini key": configured("GEMINI_API_KEY"),
        "Exotel account SID": configured("EXOTEL_ACCOUNT_SID"),
        "WSS username": configured("TELEPHONY_USER"),
        "WSS password": configured("TELEPHONY_PASSWORD"),
        "Inbound phone number": configured("SUNOCARE_PHONE_NUMBER"),
    }
    for label, ready in checks.items():
        print(f"{'SET' if ready else 'MISSING'} {label}", flush=True)
    print("Configuration presence does not verify credentials or a real call.", flush=True)
    provider_ok = asyncio.run(live_checks()) if args.live else True
    if not args.live:
        print("Use --live to test synthetic speech and extraction. This consumes provider credits.")
    print("A real inbound call through the public WSS endpoint remains a separate acceptance test.")
    return 0 if all(checks.values()) and provider_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
