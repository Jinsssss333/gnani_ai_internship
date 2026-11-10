"""Exotel Voicebot transport. Disabled unless explicit credentials are configured."""
import asyncio
import array
import base64
import binascii
import hashlib
import hmac
import io
import logging
import os
import sys
import wave
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app import db

from app.phone_flow import PhoneConversation
from app.providers import timbre

router = APIRouter()
log = logging.getLogger(__name__)


def authorized(header: str) -> bool:
    user = os.getenv("TELEPHONY_USER", "")
    password = os.getenv("TELEPHONY_PASSWORD", "")
    if not user or not password:
        return False
    expected = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    return hmac.compare_digest(header, expected)


def wav_to_pcm(data: bytes, target_rate: int) -> bytes:
    with wave.open(io.BytesIO(data), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise ValueError("Expected mono 16-bit WAV from Timbre.")
        rate = source.getframerate()
        samples = array.array("h", source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError("Empty speech.")
    # Average each source interval when downsampling, rather than renaming WAV bytes.
    output = array.array("h")
    for i in range(len(samples) * target_rate // rate):
        start = i * rate // target_rate
        end = max(start + 1, (i + 1) * rate // target_rate)
        chunk = samples[start:end]
        output.append(round(sum(chunk) / len(chunk)))
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


@router.get("/api/telephony/status")
async def status():
    return {
        "provider": "exotel", "transport_configured": bool(os.getenv("TELEPHONY_USER") and os.getenv("TELEPHONY_PASSWORD") and os.getenv("EXOTEL_ACCOUNT_SID")),
        "phone_number": os.getenv("SUNOCARE_PHONE_NUMBER", ""),
        "languages": ["hi-IN", "en-IN"], "live_call_verified": False,
    }


@router.websocket("/api/telephony/exotel")
async def exotel(websocket: WebSocket):
    account = os.getenv("EXOTEL_ACCOUNT_SID", "")
    if not account or not authorized(websocket.headers.get("authorization", "")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    queue = asyncio.Queue(maxsize=8)
    playback = asyncio.Event()
    pending_mark = ""
    stream_id = ""
    rate = 16000
    busy = False
    engine = None
    worker = None
    last_sequence = -1
    call_sid = None
    cache = Path(os.getenv("TTS_CACHE_PATH", str(Path(__file__).resolve().parents[1] / "cache" / "tts")))

    async def speak(text, language):
        nonlocal pending_mark
        digest = hashlib.sha256((language + os.getenv("TIMBRE_VOICE", "Nalini") + os.getenv("TIMBRE_MODEL", "timbre-v2.5") + text).encode()).hexdigest()
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"{digest}.wav"
        if path.exists():
            audio = path.read_bytes()
        else:
            audio, _ = await asyncio.wait_for(timbre.synthesize(text, language), 15)
            # Validate before caching; unique temporary path prevents concurrent partial reads.
            wav_to_pcm(audio, rate)
            temp = cache / f"{digest}.{uuid4().hex}.tmp"
            temp.write_bytes(audio)
            temp.replace(path)
        pcm = wav_to_pcm(audio, rate)
        await websocket.send_json({"event": "clear", "stream_sid": stream_id})
        playback.clear()
        pending_mark = uuid4().hex
        for start in range(0, len(pcm), 3200):
            chunk = pcm[start:start + 3200]
            chunk += b"\0" * (-len(chunk) % 320)
            await websocket.send_json({"event": "media", "stream_sid": stream_id,
                                       "media": {"payload": base64.b64encode(chunk).decode()}})
        await websocket.send_json({"event": "mark", "stream_sid": stream_id, "mark": {"name": pending_mark}})
        await asyncio.wait_for(playback.wait(), len(pcm) / (rate * 2) + 15)

    async def consume():
        nonlocal busy
        try:
            busy = True
            await engine.welcome()
            busy = False
            while not engine.done:
                stage, field, digit = await queue.get()
                if stage != engine.stage or field != (engine.session or {}).get("state"):
                    continue
                busy = True
                await engine.digit(digit)
                busy = False
            await websocket.close(code=1000)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log auth headers, audio, patient transcripts or provider exception bodies.
            log.warning("Phone workflow failed: %s", type(exc).__name__)
            await websocket.close(code=1011)

    try:
        while True:
            event = await asyncio.wait_for(websocket.receive_json(), 60)
            if not isinstance(event, dict):
                raise ValueError("Invalid event")
            kind = event.get("event")
            if kind == "start":
                if engine is not None:
                    raise ValueError("Duplicate start")
                start = event["start"]
                if not hmac.compare_digest(str(start.get("account_sid", "")), account):
                    raise ValueError("Wrong account")
                media = start["media_format"]
                rate = int(media["sample_rate"])
                if rate not in {8000, 16000, 24000} or str(media.get("bit_rate")) != "16" or media.get("encoding") != "audio/x-raw":
                    raise ValueError("Unsupported PCM format")
                stream_id = str(start["stream_sid"])
                candidate = str(start["call_sid"])
                if not candidate or len(candidate) > 128 or not db.start_phone_call(candidate):
                    raise ValueError("Duplicate or invalid call")
                call_sid = candidate
                engine = PhoneConversation(speak, rate, call_sid)
                worker = asyncio.create_task(consume())
            elif kind == "mark" and event.get("mark", {}).get("name") == pending_mark:
                playback.set()
            elif kind == "media" and engine and engine.listening:
                encoded = event["media"]["payload"]
                if len(encoded) > 140000:
                    raise ValueError("Audio frame too large")
                if engine.add_audio(base64.b64decode(encoded, validate=True)):
                    engine.listening = False
                    if not queue.full():
                        queue.put_nowait((engine.stage, (engine.session or {}).get("state"), "1"))
            elif kind == "dtmf" and engine and engine.stage != "PROCESSING":
                sequence = int(event.get("sequence_number", -1))
                if sequence <= last_sequence:
                    continue
                last_sequence = sequence
                digit = str(event.get("dtmf", {}).get("digit", ""))
                if digit in "0123456789*#" and len(digit) == 1 and not queue.full():
                    queue.put_nowait((engine.stage, (engine.session or {}).get("state"), digit))
            elif kind == "stop":
                break
    except (WebSocketDisconnect, TimeoutError):
        pass
    except (ValueError, KeyError, TypeError, binascii.Error):
        await websocket.close(code=1008)
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        if call_sid:
            db.end_phone_call(call_sid)


@router.get("/api/telephony/calls")
async def calls():
    return db.list_phone_calls()
