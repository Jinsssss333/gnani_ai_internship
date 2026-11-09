"""Explicit live smoke test; consumes Gnani credits using synthetic speech."""
import asyncio
import array
import io
import wave
import httpx
from dotenv import load_dotenv
from app.providers import prisma, timbre


async def main():
    load_dotenv()
    try:
        audio, kind = await timbre.synthesize("यह एक परीक्षण है। मरीज की उम्र छब्बीस साल है।", "hi-IN")
        print("Timbre:", len(audio), "bytes;", kind, flush=True)
        with wave.open(io.BytesIO(audio), "rb") as source:
            rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
            print("WAV:", rate, "Hz; channels:", channels, "width:", width, flush=True)
            if width != 2:
                raise ValueError("Expected 16-bit PCM")
            samples = array.array("h", source.readframes(source.getnframes()))
        converted = array.array("h", (samples[int(i * rate / 16000) * channels]
            for i in range(int(len(samples) / channels * 16000 / rate))))
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            target.writeframes(converted.tobytes())
        text = await prisma.transcribe(output.getvalue(), "synthetic-test.wav", "audio/wav", "hi-IN")
        print("Prisma transcript:", ascii(text), flush=True)
    except httpx.HTTPStatusError as exc:
        print("Provider HTTP status:", exc.response.status_code, flush=True)
        raise SystemExit(1)
    except Exception as exc:
        print("Test failed:", type(exc).__name__, flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
