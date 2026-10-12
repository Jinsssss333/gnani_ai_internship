# SwarSathi — ASHA voice visit register

SwarSathi is a mobile-first web prototype for capturing a home-visit note by voice, reviewing the structured fields, and saving a synthetic/demo register entry. The app can hold a recording in the browser while offline; transcription and model processing happen after the device reconnects.

## Stack

- **Frontend:** React, TypeScript, Vite, browser `MediaRecorder`, a small service worker, and IndexedDB for the local visit queue.
- **Backend:** Python, FastAPI, Pydantic, HTTPX, and SQLite.
- **Gnani providers:** Prisma for transcription, an Evon v3.3 inference endpoint for extraction, and Timbre for read-back audio.

The browser never receives provider keys. The UI marks the sample extractor and synthetic sample entries clearly. The demo parser is only a development fallback; it is not Evon.

## Run locally (PowerShell)

Open two terminals from the project root.

### Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API's interactive page is at `http://localhost:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Grant microphone permission to record. Use **Try sample note** to exercise review and save without making a model call. For microphone access from a phone, serve the app over HTTPS on the phone's network; browsers restrict microphone access on non-secure remote origins. For a phone preview, set `VITE_API_BASE_URL` in `frontend/.env.local` to the backend's reachable HTTPS address and add the frontend origin to `FRONTEND_ORIGINS` in `backend/.env`.

## Connect Gnani services

Copy `backend/.env.example` to `backend/.env`, then fill in the values from your Gnani dashboard:

- `PRISMA_API_URL` and `PRISMA_API_KEY_ID`
- `TIMBRE_API_URL` and `TIMBRE_API_KEY`
- `EVON_CHAT_COMPLETIONS_URL` for an Evon inference server exposing an OpenAI-compatible chat-completions endpoint; `EVON_API_KEY` is optional

The Prisma multipart fields, Timbre payload, endpoint, model identifier, and authentication format can vary by account/API version. Confirm these against your active dashboard before using credits. The current provider adapters are isolated in `backend/app/providers/` so their request formats can be adjusted without changing the UI.

Gnani's internship guide currently describes Evon v3.3 as open weights to run yourself rather than a hosted API. Running it requires model access and a suitable inference machine. Until an endpoint is configured, the app uses a clearly labelled demo extractor.

## Offline behavior

- The service worker caches the app shell after the first online load.
- New recordings are stored in IndexedDB with a visible **Waiting to sync** status.
- When connected, use **Sync now** or **Process recording** to submit queued audio.
- Confirmed visit records are stored in the backend's SQLite database. The browser's queue is local to that browser/device.
- The prototype uses synthetic records. Do not put real patient information into the demo.

Background sync is intentionally manual in this prototype. Keep the app open and use **Sync now** after reconnecting.

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
