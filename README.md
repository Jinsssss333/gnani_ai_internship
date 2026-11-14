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
- **Supervisor:** React, TypeScript and Vite. Register, draft recovery, evidence, call log and period exports.
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
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
if (!(Test-Path .env.local)) { Set-Content .env.local 'VITE_API_BASE_URL=http://127.0.0.1:8003' }
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

## Review, recover and export

- The register refreshes every three seconds. In progress means an active call; Needs review means unfinished documentation; Submitted means a finalized record. A home visit that could not be carried out can still have a submitted record.
- Symptom details show reported symptoms and, when present, **Symptoms denied** for explicitly ruled-out symptoms. The denied-symptoms line is hidden when empty; an empty list does not establish that other symptoms are absent.
- Open a draft to resolve its next missing answer. Complete the required fields, then choose **Confirm and submit visit**. Active calls cannot be edited from the dashboard.
- Phone review reads one field at a time: **1 next, 2 edit, 3 repeat, 9 finish reviewing**. The final menu offers **1 submit, 2 review again, 9 draft**. Instructions repeat after inactivity. Editing visit completion rechecks the newly applicable patient fields.
- Age and follow-up date offer **4** for keypad input. Date: eight digits **DDMMYYYY**; age: digits then **#**. Press **\*** to clear. Dates are spoken day/month/year and stored as ISO dates.
- Expand **Export submitted visits** in the register. Choose From and To dates, or leave either blank for an open-ended range. Both boundary dates are included using the record's creation date in **Asia/Kolkata**, not its follow-up date or final submission time.
- **Download Excel** produces a genuine `.xlsx` workbook with filters, frozen headers and wrapped cells. **PDF / Print** opens a report; click **Print / Save as PDF** and select **Save as PDF** in your browser. Pop-ups must be allowed. PDF is a browser print workflow, not an automatic PDF download.
- Exports contain all loaded, non-deleted submitted visits in the selected period, independent of the status filter. They include patient details, symptoms, follow-up, notes, visit outcome/reason and existing vitals. Drafts, call audio and audit events are excluded. The local register API returns the full submitted history without the former 100-record cap.

Latest verification and known limitations (14 November 2026):

- 22 offline backend tests passed before the export addition, including call corrections, draft recovery, finalization and gateway access checks.
- Frontend production build passed after the symptom display update on 12 November. The service-worker syntax check previously passed on 11 November.
- Live Hindi Timbre → Prisma round-trip, Gemini age extraction and English Timbre generation passed on 14 November.
- Gemini uses `gemini-3.5-flash-lite` with the existing key. Live synthetic age correction, symptom negation and Hindi Timbre → Prisma → Gemini age extraction passed. These smoke tests do not establish general extraction accuracy.
- Real Exotel calls have reached the form and created records. Name transcription accuracy remains under investigation: clearly spoken Akash was transcribed differently; extraction now preserves name candidates for explicit caller confirmation. Do not assume provider smoke tests prove recognition accuracy.
- Completed real calls were recorded on 11–13 November. On 14 November, one call reached the gateway and ended incomplete after about 18 seconds; subsequent reported attempts did not appear in the tunnel or gateway logs. The latest call problem remains unresolved.
- On 14 November, the local services and public tunnel responded successfully. An unauthenticated public WebSocket probe reached the gateway and was rejected with HTTP 403 as expected. This checks routing and authentication enforcement, not a successful authenticated call. Services must be checked again after restarting the computer.

For a silent or disconnected call, compare the latest Exotel call's applet execution details with ngrok requests and gateway logs. If no WebSocket request arrives, inspect the assigned flow and Voicebot endpoint. If a request arrives, check its handshake status and gateway error. Keep gateway output captured during troubleshooting; a successful health response alone does not verify the complete phone workflow.

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
| `frontend/src/RegisterExport.tsx` | Inclusive IST period selection, Excel download and printable report |
| `backend/app/recovery.py` | Local draft recovery and supervisor answer confirmation |
| `docs/checkpoint.md` | Detailed implementation history and current limitations |
| `docs/PHONE_DEMO.md` | Account setup, WSS configuration and demo script |

Use fictional data only. Visit codes identify demo assignments; they do not authenticate a worker. Keep the supervisor local for this prototype.
