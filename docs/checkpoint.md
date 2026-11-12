# SunoCare — project checkpoint and agent handoff

Last updated: **11 November 2026, Asia/Calcutta**.

> Latest state: Exotel reaches the phone gateway and sends `connected` and `start`. The gateway now accepts the media metadata observed in the live call; the successful end-to-end voice workflow is still unverified. Earlier Save/attachment troubleshooting notes below are historical.

## How to use and maintain this document

This is the single-file context handoff requested by the user. Read it before continuing the project. It combines product decisions, implementation, operational state, validation and history. Source code and freshly observed runtime results take precedence over stale claims here.

**User instruction: “update the checkpoint” means update this file with all changes and findings since its last update.** Refresh the current state, verification results, blockers and next actions; append a dated history entry explaining changes and reasons. Preserve meaningful earlier decisions. Distinguish implemented, planned, tested, failed and unverified work. Record relevant commit IDs. Never log API keys, passwords, tokens, credential-bearing URLs or patient data. Record configuration names and presence only. Dates/times use Asia/Calcutta; do not invent exact timestamps.

This file is an operational record, not a guarantee that previously started processes still run. Check ports and configuration before starting or stopping services. Do not treat old assistant assumptions as verified facts.

## 1. Product and user intent

SunoCare (originally SwarSathi) is a Gnani internship/hackathon prototype for ASHA workers to record home visits through guided speech. Its main differentiator is confirmation and evidence: ask a question, transcribe the answer, extract the intended field, read it back, allow correction and save only after confirmation.

The user wants a working showcase, not a complete production healthcare product. Avoid unnecessary features, copy, dashboards and infrastructure. Use **synthetic patient information only**. Do not diagnose, recommend treatment or claim clinical validation.

Initial direction was a voice-recording web/mobile application with multilingual free-note extraction, offline drafts, a register and an audit trail. Rust was discussed but explicitly not required. The implemented stack is Python + React/TypeScript. The user later explicitly rejected a static/simulated calling page and requested a **real incoming telephone call** with keypad interaction. That decision supersedes simulator-first sections of the original rework document.

Current experience:

- Worker: call the configured Exotel number, choose language and form, enter visit code, answer questions, correct mistakes, submit.
- Supervisor: open the browser register to see saved visits, evidence, audit events and call history.
- Mandatory Gnani use: Prisma speech recognition and Timbre speech generation.
- Gemini performs extraction. Evon is not required and is not the active phone extractor.

User preferences:

- Make small, focused commits for easier rollback.
- Do not push unless authorized. Earlier requested push was completed; subsequent commits remain local.
- Minimal, clean UI. No filler explanations, repeated status cards, raw technical IDs in the main view or invented metrics.
- Neo-brutalist redesign was requested and planned but **not implemented**.
- User requested a three-minute presentation video of the actual caller and actual register. They explicitly declined a simulated local caller video. **No video has been created.** A real call must work before recording one.

## 2. Workspace, repository and version state

- Workspace: `C:\Users\jinsj\OneDrive\文档\Gnani_Ai`
- Shell: PowerShell on Windows; Python virtual environment under `backend/.venv`.
- Repository: `https://github.com/Jinsssss333/gnani_ai_internship.git`
- Working branch: `dev`.
- Latest implementation commit when this checkpoint was prepared: `3550e3c`.
- Before adding this document, `dev` was seven commits ahead of locally tracked `origin/dev`; no fresh remote fetch was performed for this assertion.
- Last known pushed implementation: `413f9de`.
- `frontend/tsconfig.tsbuildinfo` was already modified/generated. Leave it out of focused source/doc commits unless deliberately addressing build artifacts.
- No applicable `AGENTS.md` was found in earlier repository inspection.

Important documents:

- `docs/SUNOCARE_REWORK.md`: broad original redesign; includes earlier simulator/offline plans that are not all implemented. A notice points readers to the real phone guide.
- `docs/PHONE_DEMO.md`: phone setup, keypad walkthrough and limits. Its default local API port 8001 is superseded by the current session's port 8003 workaround.
- `README.md`: current product and tests; its claim of no Exotel account is now stale because the user has since created one. Use the operational state in this checkpoint.
- `docs/checkpoint.md`: this maintained handoff/history file.

## 3. Architecture

```text
Worker telephone
  → Exotel inbound number → App Bazaar Voicebot applet
  → public secure WebSocket through ngrok
  → phone_gateway FastAPI app, localhost:8002
  → telephony.py (authentication, PCM, playback acknowledgments, DTMF)
  → PhoneConversation (guided state machine)
       → Prisma: finished answer WAV → transcript
       → Gemini: transcript + current field → structured value + evidence
       → Timbre: prompts and read-back → WAV → wire PCM
       → SQLite sessions, visits, audit + local answer WAV storage

React supervisor, localhost:5173
  → local main FastAPI app, currently localhost:8003
  → same SQLite database
  → visits, audit events, call logs and configuration status
```

Technology: React 19, TypeScript, Vite; Python 3.11 environment; FastAPI, Pydantic, HTTPX, python-dotenv, SQLite. `google-genai` remains used by the legacy full-visit extractor. The phone extractor calls Gemini REST directly.

The public gateway exposes only `/health` and `/api/telephony/exotel` WebSocket. The supervisor and legacy write endpoints remain on the local main app. Do not tunnel the entire main API or development frontend for this demo.

An internet connection is required at the backend for model calls. The worker needs telephone service, not a smartphone web app. This is not offline telephone transcription. Legacy offline browser queues remain in old code but are not part of the current phone experience.

## 4. Key source files

| File | Responsibility |
|---|---|
| `frontend/src/main.tsx` | Mounts `Supervisor`, not legacy `App` |
| `frontend/src/Supervisor.tsx` | Read-only visits, audit, evidence and call log; polls about every 5 seconds |
| `frontend/src/supervisor.css` | Current supervisor styling |
| `frontend/src/api.ts` | Backend client; Vite API base configuration |
| `frontend/public/sw.js` | App shell caching; v2 cache, excludes `/api/`, valid JS after repair |
| `frontend/src/App.tsx`, `CallSession.tsx`, `VoiceAnswer.tsx`, `storage.ts` | Older browser capture/guided flow/IndexedDB implementation, retained but not primary entry |
| `backend/app/main.py` | Local API, provider health/config presence, guided session actions, visits, audit, legacy processing |
| `backend/app/phone_gateway.py` | Narrow public gateway with DB initialization and no API docs endpoints |
| `backend/app/telephony.py` | Exotel WebSocket framing/authentication, cached speech, audio conversion, event worker |
| `backend/app/phone_flow.py` | PhoneConversation state, per-field recording, confirmation, edit and submit |
| `backend/app/phone_fields.py` | Strict one-field Gemini extraction and deterministic date resolution |
| `backend/app/phone_prompts.py` | Human-authored Hindi and English caller prompts |
| `backend/app/questions.py`, `call_flow.py` | Shared question lookup and next-state/action rules |
| `shared/questions.json` | Form branches, types, limits and optional flags |
| `backend/app/db.py` | SQLite persistence, atomic finalization and call history |
| `backend/app/providers/prisma.py`, `timbre.py` | Gnani adapters |
| `backend/app/providers/evon.py` | Legacy full-visit extraction: Gemini when configured; otherwise optional Evon/local demo fallback |
| `backend/check_gnani.py` | Explicit synthetic Timbre → Prisma live smoke test |
| `backend/check_phone.py` | Configuration presence check; `--live` runs synthetic Gnani/Gemini checks |

## 5. Actual phone workflow

Conversation stages: `LANGUAGE`, `FORM`, `CODE`, `ANSWER`, `PROCESSING`, `CONFIRM`, `REVIEW`, `EDIT`.

1. Hindi **2**, English **4**. Only these languages have complete phone prompt sets.
2. Home-visit form **1**.
3. Four-digit seeded visit code: **4821**, **4822**, or **7304**. Codes identify synthetic assignments; they do not authenticate workers.
4. `visit_done`: **1** yes / **2** no, followed by confirmation.
5. Completed branch: `patient_name` → `age` → optional `symptoms` → `followup_needed` → date if yes → optional `notes`.
6. Not-completed branch: `not_done_reason` (house locked/patient away/refused/other) → `followup_date` → optional `notes`.
7. For speech answers, wait for the prompt, speak, press **1** to finish. **2** repeats the question and clears the in-progress recording. **9** skips optional questions.
8. Read-back: **1** confirms/continues; **2** requests a replacement; **3** repeats the read-back.
9. Final review: **1** reads answers, **2** offers editable fields, **3** submits.
10. Submission writes the final visit and audit event in one transaction, then announces success. The supervisor displays the saved record after polling.

Editable final-review fields: patient name, age, symptoms, follow-up date and notes. Do not imply every branch decision can be edited at final review. BP/temperature existed in the original free-note idea and legacy schema, but the current phone form does not collect these as guided fields.

Audio capture caps at 25 seconds per answer, then processes automatically. Keypad boolean/enum answers bypass STT/LLM. Voice answers invoke real Prisma and Gemini; no silent synthetic fallback. Three processing failures end the call without submitting. The shared question JSON's `max_attempts` is not a universal implementation guarantee; inspect the phone engine's actual retry behavior.

## 6. Extraction and confirmation

- Current configured/default model: **`gemini-3.5-flash-lite`**.
- Existing Gemini key was retained when changing models.
- Phone extractor uses REST `generateContent`, JSON schema output and strict Pydantic validation.
- It rejects malformed responses, coerced age/boolean types, empty symptom information, missing evidence and invalid dates.
- Evidence must be a nonempty exact substring of the original transcript.
- Prompt requests latest explicit correction, no invented facts, unrelated speech ignored, and separate reported/negated symptoms.
- Age range: 0–120.
- Dates use the current IST date; one of weekday, day offset or ISO date must be supplied. Bare weekdays resolve to the next occurrence (same weekday means next week). Past dates are rejected; ambiguous phrases should request repetition.
- Symptom read-back announces structured present/absent symptoms, rather than reading background chatter as if it were saved data.
- Low thinking is conditionally configured if choosing `gemini-3.8-flash`; current 3.5 Flash-Lite does not use that override. Deprecated temperature sampling was removed from the phone request.

These rules reduce errors; they do not prove perfect extraction. A small successful symptom test returned `fever` from `mild fever`, showing qualifier fidelity still needs evaluation. Test code-mixing, corrections, dates and noisy recordings before claiming broad accuracy.

## 7. Telephony protocol and storage

Gateway authentication: Basic Auth from `TELEPHONY_USER`/`TELEPHONY_PASSWORD`, plus account SID validation on the Exotel start event. These are locally chosen gateway credentials, not the Exotel REST API key/token. Exotel REST API credentials are not currently needed for inbound routing.

Protocol accepts mono signed 16-bit little-endian raw PCM at 8, 16 or 24 kHz. Request 16 kHz via `?sample-rate=16000`. Exotel events include start/media/dtmf/mark/stop; outgoing clear/media/mark. Timbre WAV is converted to wire PCM. Every outgoing chunk, including the tail, is padded to 3,200 bytes. Prompt completion waits for its mark acknowledgment before recording. Stale queued keypad actions are checked against stage/question; duplicate DTMF sequence numbers are ignored.

TTS prompts are cached by text/language/voice/model under `backend/cache/tts`. A unique temporary file avoids partially read concurrent cache writes. Provider errors are logged by class rather than dumping credentials or transcripts.

SQLite defaults to `backend/data/visits.db`; relative `DATABASE_PATH` resolves against the backend folder, not arbitrary shell cwd. Connections close in a context manager.

| Table / storage | Data |
|---|---|
| `visit_cards` | Seeded synthetic visit codes |
| `call_sessions` | Current question/status, answer JSON, timestamps, finalization receipt |
| `phone_calls` | Call SID, linked session, started/ended times, completion outcome |
| `visits` | Structured visit JSON, transcript, language, extraction source, soft-delete metadata |
| `audit_events` | Visit action, timestamp, summary, actor |
| `backend/storage/audio/<session>/<answer>.wav` | Finished per-answer audio before provider processing |

Answer evidence includes value, transcript, quote, provider names, audio reference, confirmation flags and prior attempts. Corrections invalidate old confirmation and preserve prior evidence. Finalization validates the active branch, uses `BEGIN IMMEDIATE`, creates one visit + creation audit and caches the receipt. A repeated finalization returns that receipt.

Limits: unfinished microphone audio is in memory and lost on disconnection; finished WAVs persist. Failed model attempts may leave audio without structured evidence. Partial sessions persist but no automatic resume or partial-session editing UI exists. No browser audio playback/retention cleanup is implemented. Audit events are application records, not tamper-proof evidence. Legacy creation/update/delete APIs remain local; current supervisor is read-only.

## 8. Configuration and live account state

Secrets are in ignored `backend/.env`; frontend API address in ignored `frontend/.env.local`. Never commit either or paste their contents.

| Setting | Last observed state |
|---|---|
| `GNANI_API_KEY_ID` | Updated by user; successfully used by both services |
| `PRISMA_API_KEY_ID`, `TIMBRE_API_KEY_ID` | Cleared; both now fall back to shared Gnani key |
| `GEMINI_API_KEY` | Existing key retained and live-tested with 3.5 Flash-Lite |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` |
| `EXOTEL_ACCOUNT_SID` | Filled by user |
| `TELEPHONY_USER`, `TELEPHONY_PASSWORD` | Filled; accepted by restarted local gateway |
| `SUNOCARE_PHONE_NUMBER` | Filled and syntactically valid E.164; ownership/routing not thereby verified |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8003` in this session |

Service-specific Gnani keys override the shared key; this was explicitly checked and corrected. Presence-only `/api/health` is not a live provider test. Exotel status's `live_call_verified` is currently hardcoded false, not an automatic verification detector.

User created an Exotel account and screenshots show the Voicebot applet is available in the `Suno_care` flow. Do not keep saying they have no account. Full activation/number-to-flow mapping and a real successful call remain unverified. Generic claims that all trial inbound calls require one of ten whitelisted numbers were not verified. Official docs have differing general trial/PIN and Voicebot/KYC guidance; actual account behavior is what matters.

Credentials appeared in past chat/screenshots. Rotation was recommended, but completion is not verified. Do not reproduce those values here or in video. A credential-bearing URL was saved locally at `C:\Users\jinsj\AppData\Local\Temp\sunocare-voicebot-url.txt`; it is not a repository artifact and must not be committed or shown in footage. It may become stale after a password/domain change. URL-encode credentials in that URL; leave original values in `.env`.

## 9. Running locally and tunnel status

Default docs used 8001 for the main API, but an older process occupied it and returned 404 for `/api/telephony/status`. The current main app was started on **8003**, and frontend configuration was updated/verified. Do not indiscriminately kill other Python processes.

Run from `backend` in separate terminals as needed (activation is optional):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003
.\.venv\Scripts\python.exe -m uvicorn app.phone_gateway:app --host 127.0.0.1 --port 8002
```

Frontend: from `frontend`, `npm run dev`; preview at `http://127.0.0.1:5173`. Make sure port 8003 is included in the frontend base URL. Main API CORS permits the 5173 local frontend origins.

ngrok was installed with winget (`Ngrok.Ngrok`, installed version reported 3.3.1). Existing PowerShell did not resolve its PATH alias. Working explicit executable location:

```powershell
$ngrokExe = 'C:\Users\jinsj\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe'
& $ngrokExe http 8002
```

The user configured an ngrok authtoken locally. Do not ask them to paste it. Latest tunnel inspection: HTTPS public domain `verdict-empty-prepaid.ngrok-free.dev`, forwarding to `http://localhost:8002`. This domain is runtime-specific; rediscover from `http://127.0.0.1:4040/api/tunnels` before reuse.

Exotel URL shape, placeholders only:

```text
wss://<encoded-user>:<encoded-password>@<current-public-domain>/api/telephony/exotel?sample-rate=16000
```

Keep ngrok and gateway running. Voicebot must map to the intended ExoPhone. Suggested Next applet is Hangup; whether this resolves Save was not confirmed. Encrypt DTMF should remain off for this implementation. Recording the synthetic call is optional and useful for the requested video.

## 10. Verification: what actually passed

Latest implementation regression run: **15 tests passed** with one Starlette/httpx deprecation warning. Backend tests include branch routing, replacement confirmation, full synthetic phone flow with final edit, duplicate finalization, malformed extraction, evidence validation, dates, negation, audio cap/framing, rejected unauthorized sockets, mocked Exotel handshake/keypad, and public gateway route isolation.

```powershell
# From backend:
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe check_phone.py
.\.venv\Scripts\python.exe check_phone.py --live
.\.venv\Scripts\python.exe check_gnani.py
# From frontend:
npm run build
node --check public/sw.js
```

Tests have stalled inside the tool sandbox in prior turns but passed outside it; do not diagnose an app deadlock from sandbox behavior alone. `pytest` was installed from the already declared dependency. No new suite rerun was necessary for documentation-only work.

Verified live:

- Updated shared Gnani key: Timbre produced valid 48 kHz mono 16-bit WAV; Prisma transcribed synthetic Hindi speech including age 26.
- Gemini 3.5 Flash-Lite: corrected age 25 → 26 and separated reported fever from negated cough.
- Hindi Timbre → Prisma → Gemini age extraction passed; English Timbre prompt passed.
- Frontend production build and service-worker syntax check passed after repairs.
- Local gateway accepted configured Basic Auth via a WebSocket connection, without starting a call.
- Current public ngrok `/health` returned HTTP 200 and expected `{"status":"ok"}`. No credentials were sent in that request. This verifies public HTTPS forwarding to SunoCare, not authenticated WSS or Exotel routing.

Not verified: real Exotel call, real caller DTMF/media/mark timing, call-to-register completion, noise robustness, broad multilingual extraction, video recording, successful Exotel flow Save.

## 11. Current blocker — Exotel Save stuck at 0%

The user pasted generic troubleshooting suggesting WebSocket failure. They initially answered “after dialing,” then explicitly corrected this to **“after pressing saving.” Use the latest correction.** Do not assume an active call is failing.

Latest diagnostics (10 November 2026):

- Local gateway `/health`: 200.
- ngrok local API: 200, tunnel targets port 8002.
- Public tunnel `/health`: 200, expected SunoCare body.
- Available ngrok request log showed only our `/health` request; no observed Exotel WebSocket request.
- Pasted terminal log includes successful authtoken saving, online session and forwarding; it also contains the historical PATH error. No `ERR_NGROK` string was found. Do not confuse the earlier PATH error with current tunnel failure.

Conclusion: tunnel shutdown/general public HTTP reachability is ruled out **at the time tested**. Exotel authenticated WSS has not been proven or disproven. A Save UI failure may be form validation, flow completeness, permissions/account state or a dashboard request failure; these are hypotheses, not findings.

Next diagnostic: obtain the actual 0% screen or inspect the browser's failing save request/validation message with credentials hidden. Confirm whether a Hangup successor exists, exact flow Save response and number assignment. Do not repeatedly change AI keys or rebuild the backend without evidence.

An automatic approval review previously rejected a direct public WebSocket authentication test because it would transmit Basic Auth credentials through the third-party ngrok tunnel without sufficiently explicit authorization. That authenticated public test **was not performed**. Do not retry by disguising it. Local authentication tests and unauthenticated public health requests were completed as safer alternatives. An Exotel-mediated call remains the intended verification path; if a direct public credential test becomes necessary, explain the transmission and obtain the required explicit authorization.

## 12. UI and video work still planned

The current visible UI is the real read-only supervisor. No phone dialer is mounted. It polls visits, audit, telephony status and calls; evidence shows transcript, quote, confirmation and previous answers. Current page still has explanatory copy and raw IDs the user wants reduced.

Approved direction for a future UI rework: restrained neo-brutalism (off-white, black borders, hard shadows, bold type, one yellow accent). Keep header with small synthetic-demo badge/status; tabs Visits/Calls/Audit; compact dial-in strip; useful register columns; evidence side panel. Remove slogans, hero filler, repeated metrics/statuses and technical IDs from primary view. Do not invent records or fake live connection states. This is a plan, not delivered code.

Three-minute video request: user insists on actual telephone interaction and actual register, not AI-generated footage or a simulated caller. No recording has started. ffmpeg and ffprobe are installed. Plan after first successful call: capture language/code, short answers, one correction, submit, then saved visit/evidence/audit. Hide credentials and use fictional patient information. Coordinate real phone audio capture with user; do not claim the agent can independently operate their physical phone.

## 13. Change history and decisions

Earlier conversation history, not all independently re-tested now:

- SwarSathi began as a voice note capture app. User requested a dashboard, mock worker identity, register, audit, delete/edit, offline queues and minimal navigation.
- User reported accumulating drafts, stuck processing, disabled clearing, symptom comma/edit problems and excessive notification/copy. Legacy UI work preceded the current phone pivot; do not assume every old feature remains mounted.
- Project renamed SunoCare during repository rework. React/Python chosen rather than Rust.
- Evon extraction was unsuitable/unavailable for user. Gemini selected as permitted alternative; Gnani retained for STT/TTS.
- User pulled rework docs and requested hackathon scope and small commits.
- Guided caller decisions adopted: per-field speech, DTMF confirmation, final correction and evidence, then real telephone transport instead of browser simulation.

Verified recent Git history:

| Commit | Change |
|---|---|
| `44f673d` | Earlier SunoCare updates baseline; inspect Git for exact contents |
| `6db1de8` | Guided replacement confirmation and final-review edits |
| `d8e79c1` | Explicit live synthetic Gnani round-trip checker |
| `7a30856` | Guided browser recording connected to Prisma/Timbre |
| `413f9de` | Exotel caller transport, phone workflow and supervisor; last known pushed implementation |
| `65c34d0` | Exotel playback tail frame minimum-size fix |
| `67aa54a` | Strict extraction validation and structured symptom read-back |
| `2000972` | Service-worker JS repair; API data excluded from cache |
| `60debdf` | Phone-only public gateway isolated from supervisor/write APIs |
| `5f1acd8` | Phone setup docs and live provider preflight |
| `f426c83` | Attempted Gemini 3.8 Flash migration; deprecated sampling removed, low thinking option |
| `3550e3c` | Switched to verified Gemini 3.5 Flash-Lite after failed alternatives |

10 November operational/model history:

1. Argon (`gemini-4-argon`) returned HTTP 429; user stated they lack access.
2. Gemini model-list request using existing key succeeded. 3.8 Flash was listed, but live extraction timed out/returned 503; listing alone did not prove inference access.
3. 2.5 Flash and 2.5 Flash-Lite returned 404 in live attempts despite appearing in the list.
4. 3.5 Flash-Lite passed small live examples and full synthetic provider preflight; selected and committed. Do not revert to Argon/3.8 by following older messages.
5. User updated Gnani key. Initial tests still used service-specific overrides. After clearing them, both services were confirmed using the new shared key and passed.
6. Started preview/main API/gateway; discovered old port 8001 server; moved current local API to 8003 and verified frontend picked it up.
7. User created Exotel account, accessed Voicebot applet and filled SID/credentials/number. Placeholder password/number were detected and corrected; E.164 syntax passed. Gateway was restarted and local authenticated connection passed.
8. Installed ngrok, resolved PATH confusion by providing explicit executable path, user configured account/token and ran tunnel.
9. Saved encoded private Voicebot URL locally; user pasted it into applet. Password was visible in screenshot; recommended changing it. Do not assert rotation completed.
10. User reported 0% on Save. Latest public HTTP test passed; no Exotel request observed. Exact dashboard failure remains undiagnosed.
11. User requested this single maintained checkpoint and the convention that “update the checkpoint” logs subsequent work. Created this file with current history and diagnostics; no product code was changed for this documentation task.

## 14. Next actions in priority order

1. Diagnose the Exotel **Save** failure from actual validation/network evidence. Preserve the working provider and tunnel configuration.
2. Save the flow, map the intended ExoPhone, then make one actual synthetic call. Check incoming socket/logs without exposing auth headers.
3. Verify Hindi/English greeting, DTMF, audio capture, extraction/read-back, correction, one final saved visit and audit, and call completed status. Also test hangup without submit.
4. Address only failures evidenced by those tests; keep commits small.
5. Implement minimal neo-brutalist supervisor UI if still desired before filming; do not let cosmetic work substitute for real-call verification.
6. Record the requested three-minute actual demo once end-to-end calling works.
7. Update this checkpoint with every requested checkpoint refresh, explicitly marking newly resolved blockers and retaining remaining limits. Push only when asked.

## 15. 11 November update — Exotel troubleshooting

- Services were restarted on ports 5173 (frontend), 8003 (main API) and 8002 (gateway). ngrok initially lacked its saved auth configuration; the user reconfigured it and the tunnel was restarted. Public `/health` returned 200 with the expected body. Runtime availability must still be checked anew.
- Exotel's `map_vn_with_flow` request returned HTTP 200 with application body `{"error":true,"message":"Invalid Exophone/Phonenumber"}`. The UI remained at 0% instead of showing the error. This is number-to-flow attachment rejection, not evidence of a model or tunnel failure.
- Chrome also paused on an exception in Facebook tracking code (`fbevents.js`, parsing `get started` as a URL). Disabling exception pauses did not fix the attachment rejection.
- Suggested workaround: back up and edit the existing demo Landing Flow already attached to the trial number, rather than remapping the number. Completion and a full real call are not established in this chat.
- Repository inspection found existing commit `c60f313` (safe Exotel diagnostics) plus an uncommitted compatibility change accepting alternate base64/bitrate metadata. That change was preserved in a separate dev commit. It is existing workspace work, not proof that a real call succeeded.
- Fetched `origin --prune`: local dev contained the fetched origin/dev history and was one commit ahead before saving the remaining changes. No conflict or missing remote commit was found.
- Validation of the preserved baseline: 15 backend tests passed when run from `backend`. An initial invocation from repository root failed import collection (`app` not found); correcting cwd resolved it without code changes.


## 16. 11 November — recoverable call records and review rework

### New evidence
The user reports a real Exotel call reached the form but failed around the follow-up date. The running supervisor now visibly shows that actual call session under Needs review, with earlier answers retained and followup_date unresolved. This confirms recoverability, not a successful complete live submission. The exact failed STT versus extraction step was not established.

### Implementation
- Current checkout is dev. Exotel remains the runtime provider; no provider switch or credential changes were made.
- Phone review now reads one field at a time: 1 next, 2 edit a supported field, 3 repeat, 9 finish reviewing. Instructions are spoken on entry, invalid input, or inactivity rather than for every field. Boolean/outcome fields remain immutable from review; the bot explains this.
- Finish menu: 1 submit, 2 review again, 9 draft. Submission retains atomic validation/idempotency. A missing required answer results in a clearly announced draft, never a false successful submission.
- Ten-second inactivity reminders in keypad/review stages; after two reminders, the third timeout saves a draft and ends. Recording waits up to 30 seconds (25-second audio cap), so review timeout does not truncate a normal voice answer.
- Exotel DTMF sends clear and releases pending playback. Revision-tagged queue entries reject stale presses except multi-digit code/date entry. Provider integration tests interrupt an unacknowledged playback mark.
- Age/date offer key 4 for keypad fallback. Date is DDMMYYYY, automatically processed at eight digits; age uses digits then #. Star clears. Dates reject invalid/past values, use IST, read back day/month/year, store ISO. Full spoken dates accept either day-first or month-first order via Gemini; not yet revalidated with a real call.
- At the spoken date question, 9 leaves the date unresolved and continues; missing dates still prevent final submission. At answer stage, 0 saves a draft.
- Existing optional symptoms and notes remain optional for backward compatibility; no new clinical fields or specialised forms were introduced.
- New local-only recovery router: GET /api/register/sessions lists unfinished sessions, live status, answers, and next missing field. POST /api/register/sessions/{id}/answer lets supervisor confirm the next missing field with validation, prior-answer history, and an audit event. Active calls and completed sessions cannot be repaired here. Supervisor correction is sequential missing-field recovery, not an unrestricted editor.
- Draft completion uses existing POST /api/calls/{id}/finalize. Submitted sessions disappear from pending and appear once in visits. Visit failure reason now persists in the final record.
- The public phone gateway still does not mount supervisor/recovery routes.
- Dashboard rebuilt as a minimal responsive sidebar with Register, Calls, Audit. Filters: All, In progress, Needs review, Submitted. It polls every three seconds with bounded requests and no overlapping refresh; audit/phone-log failures do not prevent register updates. Selected drafts expose missing-field entry and final submit; submitted evidence remains readable. Existing records are preserved.

### Validation and runtime
- Backend tests run from backend with .venv/Scripts/python.exe -m pytest tests -q. Initial root invocation failed imports; sandbox async runner hung; the correctly scoped unsandboxed run passed. The hung test processes were stopped after identification.
- Regression coverage includes date entry/invalid dates, per-field review/repeat/reminder, draft persistence, active-call editing rejection, and draft repair -> idempotent submission -> refreshed register data.
- Frontend TypeScript/Vite production build passed. Browser inspection verified the redesigned page, existing submitted records, recovered real-call draft, and date repair control. No real patient data or new sample records were added to the working database.
- Started local API 8003, gateway 8002, Vite 5173 as hidden processes. Frontend .env.local already targets 8003. Gateway uses the existing provider credentials. Tunnel availability and a fresh real call still require validation before a demo.
- No remote push. Changes are saved in focused local commits.

## 17. 11 November — correct visit branching during phone review

- The latest real call was saved with confirmed visit_done=false (keypad input 2) and not_done_reason=refused. Consequently it legitimately followed the unsuccessful-visit branch: reason, follow-up date, notes. The evidence establishes the stored choice, not whether the user intended that choice.
- Found a recovery limitation: final review previously prohibited changing visit_done/followup_needed and listed only previously captured patient fields. This is now fixed. Every active field, including branching answers and absent active fields, can be selected for correction.
- After correcting a branching answer, the API walks the newly active path and asks every unresolved field before returning to review. Changing unsuccessful to successful therefore requires name, age, symptoms (or explicit optional skip), and follow-up choice. Historical answers stay stored, but irrelevant branch fields are excluded from spoken review and final evidence.
- Before entering review, the phone flow now directs missing required answers back to their question. Explicit draft saving remains available; a required missing date cannot silently pass submission.
- Opening prompts in both languages now explain that 1 means the patient visit was carried out and leads to patient details; 2 means it could not be carried out. The negative read-back explicitly explains that patient fields will be skipped and offers correction.
- Validation: 21 tests passed, including unsuccessful-to-successful correction, missing patient submission rejection, active review filtering, and missing date recovery. A fresh real call is still needed to verify the revised spoken interaction.
- The previous four commits were pushed to origin/dev at the user's request. This follow-up fix is committed locally; it has not been pushed automatically.

## 18. 11 November — name extraction and interrupted work recovery

- User confirmed both recorded names were Akash and explicitly approved replaying those recordings through Gnani/Gemini. Replay returned `august` and `akash e`; the old extraction prompt rejected both. A focused diagnostic reproduced `The answer was unclear; please repeat it.`
- Revised the extraction instructions to treat a short standalone name-like response as a candidate, retain spelling/initials, and never guess a corrected name. Live checks with the revised prompt returned both transcripts unchanged for caller confirmation. This does not establish accurate STT recognition of Akash.
- The earlier turn hit an automatic approval usage-limit failure before tests/restart/commit. Consequently the prompt edit was left uncommitted and was not loaded in the phone server. This turn completed those steps.
- On resumption, API 8003 refused connections and no SunoCare server/tunnel processes were running. Restarted API 8003, gateway 8002, UI 5173 and the existing ngrok tunnel. Backend unavailability prevents dashboard saves; the latest two call records themselves stopped at patient_name, not finalization.
- Failed speech attempts now retain transcript, audio reference, failure stage (transcription/extraction), and prior attempts. They remain unconfirmed and awaiting replacement, preventing accidental submission of rejected answers. Speech playback happens outside the extraction error handler, so playback failures cannot overwrite a successfully extracted answer.
- All 22 local tests passed, including failed-name evidence preservation and existing draft-to-submission/idempotency coverage. Another real call is required to assess name recognition and caller experience. No historical record was modified, and no changes were pushed automatically.
