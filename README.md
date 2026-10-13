# SwarSathi — ASHA voice visit register

SwarSathi is a mobile-first web prototype for capturing a home-visit note by voice, reviewing the structured fields, and saving a synthetic/demo register entry. The app can hold a recording in the browser while offline; transcription and model processing happen after the device reconnects.

## Stack

- **Frontend:** React, TypeScript, Vite, browser `MediaRecorder`, a small service worker, and IndexedDB for the local visit queue.
- **Backend:** Python, FastAPI, Pydantic, HTTPX, and SQLite.
- **Gnani providers:** Prisma for transcription, an Evon v3.3 inference endpoint for extraction, and Timbre for read-back audio.

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

Open `http://127.0.0.1:5173`. This workspace uses backend port `8001` because port `8000` is unavailable in its Windows environment. Grant microphone permission to record. Use **Try sample note** to exercise review and save without making a model call. For microphone access from a phone, serve the app over HTTPS on the phone's network; browsers restrict microphone access on non-secure remote origins. For a phone preview, set `VITE_API_BASE_URL` in `frontend/.env.local` to the backend's reachable HTTPS address and add the frontend origin to `FRONTEND_ORIGINS` in `backend/.env`.

## Connect Gnani services

Copy `backend/.env.example` to `backend/.env`. Prisma and Timbre use the currently documented Gnani endpoints and `X-API-Key-ID` authentication. Set `GNANI_API_KEY_ID` in the local environment file; set `PRISMA_API_KEY_ID` or `TIMBRE_API_KEY_ID` only if those services have separate key IDs.

- `GNANI_STT_BASE_URL` defaults to `https://api.vachana.ai`; the backend appends `/stt/v3`. `GNANI_DEFAULT_LANG` defaults to `hi-IN`.
- Short recordings use synchronous Prisma REST. Gnani also offers batch jobs and realtime WebSocket modes, but the prototype does not use those flows.
- Set `EVON_INFERENCE_ENDPOINT` to the Evon v3.3 inference server you run; it should expose an OpenAI-compatible chat-completions endpoint. `EVON_MODEL_NAME` must match the model name served by that endpoint. `EVON_API_KEY` is optional for local development. The older `EVON_CHAT_COMPLETIONS_URL` and `EVON_MODEL` names remain accepted.

The [Prisma REST docs](https://docs.gnani.ai/api/STT/speech-to-text) document `https://api.vachana.ai/stt/v3`. The [Timbre REST docs](https://docs.gnani.ai/api/TTS/tts-inference) document `https://api.vachana.ai/api/v1/tts/inference` with model `timbre-v2.5`. Check your dashboard for account access and available credits before the first live call. The provider adapters are isolated in `backend/app/providers/` so request formats can be adjusted without changing the UI.

Evon v3.3 is an open-weight model to run yourself rather than a hosted API. Running it requires model access and a suitable inference machine. Until an endpoint is configured, the app uses a clearly labelled demo extractor.

## Offline behavior

- The service worker caches the app shell after the first online load.
- New recordings are converted and stored in IndexedDB with a visible **Waiting to sync** status.
- A reviewed visit is saved in the browser's local register immediately, even when offline. Use **Sync now** after reconnecting to copy confirmed records to the backend.
- When online, use **Sync now** or **Process recording** to submit queued audio.
- Confirmed server records are stored in SQLite. The browser keeps a local copy for offline access.
- The prototype uses synthetic records. Do not put real patient information into the demo.

Background sync is intentionally manual in this prototype. Keep the app open and use **Sync now** after reconnecting. Prisma/Timbre model calls require an internet connection.

## Project layout

```text
frontend/                 React PWA
  src/App.tsx              recording, review, queue, register UI
  src/storage.ts           IndexedDB visit queue
  src/api.ts               backend calls
  public/sw.js             offline app-shell cache
backend/app/main.py        FastAPI routes
backend/app/providers/    Prisma, Evon, Timbre adapters
backend/app/db.py          SQLite persistence
```
