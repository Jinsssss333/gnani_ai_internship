# SwarSathi — ASHA voice visit register

SwarSathi is a mobile-first web prototype for capturing a home-visit note by voice, reviewing the structured fields, and saving a synthetic/demo register entry. The app can hold a recording in the browser while offline; transcription and model processing happen after the device reconnects.

## Stack

- **Frontend:** React, TypeScript, Vite, browser `MediaRecorder`, a small service worker, and IndexedDB for the local visit queue.
- **Backend:** Python, FastAPI, Pydantic, HTTPX, and SQLite.
- **AI providers:** Gnani Prisma for transcription, Gemini for structured extraction, and Gnani Timbre for read-back audio.
- **Visit history:** IndexedDB for offline-first visit and audit storage; SQLite for synced records and audit events.

The browser never receives provider keys. The UI marks the sample extractor and synthetic sample entries clearly. The demo parser is only a development fallback; it is not Evon. Recorded browser audio is converted to 16 kHz mono WAV before Prisma upload and limited to 60 seconds, matching the documented REST workflow.

## Run locally (PowerShell)

Open two terminals from the project root.

### Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8001
```

The API's interactive page is at `http://localhost:8001/docs`.

### Frontend

```powershell
cd frontend
npm install
Set-Content .env.local "VITE_API_BASE_URL=http://127.0.0.1:8001"
npm run dev
```

Open `http://127.0.0.1:5173`. This workspace uses backend port `8001` because port `8000` is unavailable in its Windows environment. Grant microphone permission to record. Choose **Hinglish example** or **Tanglish example** and load it to inspect a synthetic structured record without making a model call. To test the real speech path, expand the code-mix phrase and read it into the microphone; after you stop, Prisma transcribes it and the extractor prepares the review fields. For microphone access from a phone, serve the app over HTTPS on the phone's network; browsers restrict microphone access on non-secure remote origins. For a phone preview, set `VITE_API_BASE_URL` in `frontend/.env.local` to the backend's reachable HTTPS address and add the frontend origin to `FRONTEND_ORIGINS` in `backend/.env`.

## Connect Gnani services

Copy `backend/.env.example` to `backend/.env`. Prisma and Timbre use the currently documented Gnani endpoints and `X-API-Key-ID` authentication. Set `GNANI_API_KEY_ID` in the local environment file; set `PRISMA_API_KEY_ID` or `TIMBRE_API_KEY_ID` only if those services have separate key IDs.

- `GNANI_STT_BASE_URL` defaults to `https://api.vachana.ai`; the backend appends `/stt/v3`. `GNANI_DEFAULT_LANG` defaults to `hi-IN`.
- Short recordings use synchronous Prisma REST. Browser echo cancellation, auto gain, and noise suppression are requested when supported by the device/browser; this is not a substitute for testing in noisy conditions. Gnani also offers real-time WebSocket mode, but this prototype does not use it, so transcript and structured fields appear after recording stops and processing completes.
- Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then set `GEMINI_API_KEY` in `backend/.env`. Set `GEMINI_MODEL=gemini-flash-latest`, or the exact Gemini model ID available to your key. Gemini takes priority for extraction when this key is present; the browser never receives it.
- Evon remains an optional fallback: set `EVON_INFERENCE_ENDPOINT` only if you later run an Evon v3.3 server.

The [Prisma REST docs](https://docs.gnani.ai/api/STT/speech-to-text) document `https://api.vachana.ai/stt/v3`. The [Timbre REST docs](https://docs.gnani.ai/api/TTS/tts-inference) document `https://api.vachana.ai/api/v1/tts/inference` with model `timbre-v2.5`. Check your dashboard for account access and available credits before the first live call. The provider adapters are isolated in `backend/app/providers/` so request formats can be adjusted without changing the UI.

Gemini returns structured JSON matching the visit schema, which is then validated before the worker reviews it. Until a Gemini key is configured, the app uses a clearly labelled local extractor.

The extraction prompt tells the model to ignore unrelated chitchat, honor negation, and prefer the latest clear correction for a field while leaving unresolved conflicts empty. The local fallback handles only common examples and corrections; it is not equally reliable with noisy or conversational notes.

## Dashboard and visit history

- The desktop sidebar switches between Dashboard, Visit register, Audit trail, and follow-ups. On narrow screens, the section switcher moves to a bottom navigation bar.
- The dashboard shows visits saved today, due follow-ups with explicit calendar dates, drafts to review, and sync status. A follow-up can be marked completed or missed.
- Visit register entries can be edited. Deleting an entry hides it from the active register and stores a deletion timestamp; the audit event remains.
- Creating, editing, deleting, and marking follow-ups creates timestamped audit events. Events are stored locally first and synced idempotently to SQLite when online.
- The worker identity and visit examples are synthetic demo data. The audit actor is a fixed demo label, not authenticated identity or a production-grade audit guarantee.

## Offline behavior

- The service worker caches the app shell after the first online load.
- New recordings are converted and stored temporarily in IndexedDB with a visible **Waiting to sync** status. The recording is removed when its draft is confirmed or discarded; confirmed visits retain the transcript and structured fields, not the audio.
- A reviewed visit is saved in the browser's local register immediately, even when offline. Pending audio, visit changes, and audit events retry automatically when the browser reports that connectivity has returned; **Sync now** remains available as a manual retry.
- Offline visit and audio queues use browser IndexedDB. SQLite is the backend store for records after sync; there is no local SQLite database in this web prototype.
- Confirmed server records are stored in SQLite. The browser keeps a local copy for offline access.
- Deleted visits are soft-deleted in SQLite, and audit events stay available after deletion.
- The prototype uses synthetic records. Do not put real patient information into the demo.

Automatic sync runs while the app is open and the browser reports a connection. If a model request still fails, the entry remains local and can be retried with **Sync now**. Prisma/Timbre model calls require an internet connection.

## Project layout

```text
frontend/                 React PWA
  src/App.tsx              dashboard, recording, review, register, and audit UI
  src/storage.ts           IndexedDB visit queue, register, and audit events
  src/api.ts               backend and sync calls
  public/sw.js             offline app-shell cache
backend/app/main.py        FastAPI routes
backend/app/providers/    Prisma, Evon, Timbre adapters
backend/app/db.py          SQLite visit and audit persistence
```
