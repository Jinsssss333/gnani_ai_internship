# SunoCare — Phone visit register

A hackathon prototype for recording **synthetic** ASHA home visits through a real phone call. The worker chooses a language, answers guided questions, hears the interpreted details, corrects mistakes and submits a confirmed record. The browser is now a supervisor view of saved visits, evidence, audit events and call history.

## Current workflow

```text
Worker calls Exotel number
  → Voicebot applet → authenticated WebSocket → FastAPI phone gateway
  → Hindi (2) / English (4) → home visit (1) → four-digit visit code
  → question → voice answer → press 1 to finish
  → Gnani Prisma transcription → Gemini field extraction
  → Gnani Timbre read-back → confirm / correct
  → final review → submit → SQLite visit + audit event
  → React supervisor refreshes from the local API
```

Keypad choices bypass speech extraction. Voice is processed after each answer, not as a live transcript. Current fields are visit completion, name, age, symptoms including negations, follow-up and notes. An incomplete home visit instead asks for its reason and next visit date.

## Stack and scope

- **Phone transport:** Exotel Voicebot/AgentStream, raw mono 16-bit PCM over WSS.
- **Backend:** Python, FastAPI, HTTPX, Pydantic and SQLite.
- **AI:** Gnani Prisma STT, Gemini extraction and Gnani Timbre TTS. Phone extraction has no demo-parser fallback.
- **Supervisor:** React, TypeScript and Vite. Read-only register, evidence and call log.
- **Persistence:** SQLite stores sessions, structured answers, transcripts, corrections and final records. Per-answer WAV files remain on the backend; browser playback of those files is not implemented.

The caller needs cellular service. Exotel and the backend need internet access. There is no offline telephone transcription or automatic resume after a dropped call. Legacy browser recorder code remains in the repository but is not the mounted UI.

## Run locally on Windows

Use the virtual environment's Python directly; PowerShell activation is optional.

```powershell
cd backend
# Only if .venv does not already exist:
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Preserve any existing credentials:
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
if (!(Test-Path .env.local)) { Set-Content .env.local 'VITE_API_BASE_URL=http://127.0.0.1:8001' }
npm run dev
```

Open [the supervisor](http://127.0.0.1:5173). Starting it alone does not provide a dialable number. Follow [Phone setup and demo](docs/PHONE_DEMO.md) to connect Exotel and run the phone gateway on port 8002.

## Check before demonstrating

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe check_phone.py
# Optional live requests using synthetic data; consumes provider credits:
.\.venv\Scripts\python.exe check_phone.py --live
```

`check_phone.py` prints configuration presence, never key values. A nonzero exit means missing setup or a failed provider check. It does not dial a phone, create a visit or verify a public WSS connection.

From `frontend`: `npm run build` and `node --check public/sw.js`.

Latest verified state (10 November 2026):

- 15 offline backend tests pass, including a mocked Exotel socket, correction, finalization and gateway access checks.
- Frontend production build and service-worker syntax check pass.
- Live Hindi Timbre → Prisma round-trip and English Timbre generation pass.
- Gemini uses `gemini-3.5-flash-lite` with the existing key. Live synthetic age correction, symptom negation and Hindi Timbre → Prisma → Gemini age extraction passed. These smoke tests do not establish general extraction accuracy.
- No Exotel account/number is configured; a real inbound call remains unverified.

## Project map

| File | Role |
|---|---|
| `backend/app/phone_gateway.py` | Public phone-only entry point |
| `backend/app/telephony.py` | Authenticated socket, PCM conversion, audio playback |
| `backend/app/phone_flow.py` | Keypad and voice conversation |
| `backend/app/phone_fields.py` | Gemini extraction with strict validation |
| `backend/app/phone_prompts.py` | Hindi and English caller prompts |
| `backend/app/db.py` | Sessions, atomic finalization, visits and audit persistence |
| `shared/questions.json` | Branching form definition |
| `frontend/src/Supervisor.tsx` | Current browser UI |
| `docs/PHONE_DEMO.md` | Account setup, WSS configuration and demo script |

Use fictional data only. Visit codes identify demo assignments; they do not authenticate a worker. Keep the supervisor local for this prototype.
