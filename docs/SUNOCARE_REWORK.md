# SunoCare — Project Rework Plan

> **SunoCare — Listen. Confirm. Care.**
> A voice-first, IVR-style visit register that lets frontline health workers (ASHA workers) complete structured home-visit records through guided speech in their own language — with transcript evidence, targeted corrections, offline drafts, and reliable sync.

Built for the **Gnani.ai Great Indian AI Internship Challenge**. Formerly **SwarSathi** — all user-facing references must be renamed to **SunoCare** (exact casing). The GitHub repo name stays `gnani_ai_internship`.

> ⚠️ Prototype using **synthetic data only**. No real patient data, no diagnosis, no treatment advice.

---

## 1. Problem

Frontline health workers often:

- Fill complex mobile forms, sometimes alongside paper registers (duplicate entry).
- Have low digital literacy or limited English.
- Work with unstable mobile data → failed syncs, lost work, re-entry.
- Get little feedback on whether their data was saved or what to do next.

## 2. Solution

Replace the form with a **guided phone-call-like flow**:

```
Call → choose language → visit code → guided questions (speak or press keys)
     → hear what was understood → confirm / correct only the wrong field
     → final read-back → save → sync → follow-up feedback
```

### Core differentiator — the accountability loop

Typical demo: `Speak → transcript → summary → save`

SunoCare: `Ask → Listen (Prisma) → Extract → Show evidence → Read back (Timbre) → Correct → Confirm → Save → Sync → Follow-up`

The system always separates: **raw transcript · interpreted value · evidence quote · worker-confirmed value · sync status**.

### Honest connectivity claims

| Mode | Needs | Use |
|---|---|---|
| **Call mode (primary)** | Cellular coverage on worker side; backend internet for Prisma/Timbre | "No app, no typing, no mobile data — just call and speak." Prototyped as a web call simulator. |
| **Offline draft mode (fallback)** | Nothing at capture time | Prompts play from **pre-generated Timbre audio cached on device**; answers saved per question in IndexedDB; transcription & extraction run after reconnection and the visit lands in **Needs review** for the worker to confirm. *(Updated — see §19 F3.)* |

Never claim AI transcription works offline.

---

## 3. Users

- **Primary — ASHA worker:** voice-first call flow, large buttons, one question per screen.
- **Secondary — Supervisor / PHC staff:** web dashboard for visits, follow-ups, sync status, audit trail.

---

## 4. Architecture

```
┌──────────────────────────── Frontend (React + TS + Vite, PWA) ───────────────────────────┐
│  Call Simulator UI ── useSpeechRecorder (MediaRecorder → 16 kHz mono WAV)                │
│        │                useCallSession (state from backend)                              │
│        │                useOfflineQueue (IndexedDB drafts + retry)                       │
│  Review / Correction / Register / Follow-ups / Audit / Supervisor views                  │
│  Service worker (app-shell cache)                                                        │
└───────────────┬──────────────────────────────────────────────────────────────────────────┘
                │ HTTPS (JSON + audio)
┌───────────────▼──────────────── Backend (FastAPI + Pydantic + HTTPX) ────────────────────┐
│  call_flow.py  — question state machine (per session)                                    │
│  services/extraction.py — one-field-at-a-time extraction                                 │
│  services/validation.py — age / BP / temp units / dates / enums                          │
│  services/audit.py, services/sync.py (versioned upserts)                                 │
│  providers/prisma.py (STT) · timbre.py (TTS) · gemini.py · evon.py (optional)            │
│  db.py — SQLite                                                                          │
└───────┬──────────────────────┬───────────────────────┬───────────────────────────────────┘
        ▼                      ▼                       ▼
   Gnani Prisma (STT)     Gnani Timbre (TTS)     Gemini / Evon (extraction)
                                                 → local parser = dev fallback only
```

**Future production path (not required for demo):** telephony provider (e.g. Exotel/Twilio) → webhook → same `call_flow.py` state machine. The web simulator and phone call share one backend.

### Gnani usage

| Service | Role |
|---|---|
| **Prisma** | Transcribes each answer (REST, clips ≤ 30 s). Languages: ml-IN, hi-IN, ta-IN, en-IN. |
| **Timbre** | Speaks prompts, per-field read-back, final summary. Format numbers/dates as words. |
| **Evon** | Optional extraction provider — not mandatory, don't self-host for the deadline. |

---

## 5. Call Flow (State Machine)

```
START → LANGUAGE → VISIT_CODE → Q_VISIT_DONE → Q_AGE → Q_SYMPTOMS
      → Q_FOLLOWUP_NEEDED → (Q_FOLLOWUP_DATE) → Q_NOTES(optional)
      → FINAL_REVIEW → SAVED
Each Q_* : ASK → LISTEN → EXTRACT → READBACK → {1 confirm | 2 correct | 3 repeat | 9 skip}
FINAL_REVIEW : {1 save | 2 correct a field | 3 restart}
```

| ID | Question | Answer type | Keypad |
|---|---|---|---|
| `visit_done` | Did you complete the home visit today? | boolean | 1 yes / 2 no |
| `age` | Patient's age? | integer 0–120 | digits |
| `symptoms` | Fever, cough, vomiting, weakness or others? | reported[] + negated[] + qualifiers | 9 skip |
| `followup_needed` | Is a follow-up needed? | boolean | 1 / 2 |
| `followup_date` | When is the follow-up? | phrase + ISO date if unambiguous | — |
| `notes` | Any extra note? | free text (optional) | 9 skip |

### Demo script

```
SunoCare: Welcome to SunoCare. For Malayalam press 1, Hindi 2, Tamil 3, English 4.
Worker:   Malayalam.
SunoCare: Say or enter your four-digit visit code.          Worker: 4821
SunoCare: Did you complete the home visit today?            Worker: Yes
SunoCare: Patient's age?                                    Worker: Twenty six
SunoCare: I recorded age 26. Press 1 to confirm, 2 to correct.   Worker: 1
SunoCare: Any symptoms?                    Worker: Mild fever and nausea. No cough.
SunoCare: I recorded mild fever and nausea. No cough. Confirm?   Worker: 1
SunoCare: Follow-up needed?                                 Worker: Yes
SunoCare: When?                                             Worker: Friday
SunoCare: Follow-up Friday. Confirm?                        Worker: 2
SunoCare: Say the correct day.                              Worker: Monday
SunoCare: Updated to Monday. Summary: age 26, mild fever and nausea, no cough,
          follow-up Monday. Press 1 to save.                Worker: 1
SunoCare: Visit saved in SunoCare. (Simulated SMS confirmation.)
```

---

## 6. Feedback Design

1. **Per-field read-back** after every answer.
2. **Evidence table** — every field shows the transcript phrase that produced it; tap to replay the answer audio (seek only if word timestamps exist).
3. **Targeted correction** — re-ask only that field; keep original + correction evidence; write an audit event.
4. **Final read-back** before `confirmed`.
5. **Worker feedback after save:** saved/synced status, offline queue count, follow-ups due today, missing-data alerts, failed-sync alerts (simulated SMS in prototype).

---

## 7. Data Model (SQLite)

```text
visit_sessions
  id UUID PK, language_code, visit_code, current_question_id,
  status: in_progress|awaiting_confirmation|completed|abandoned|failed,
  answers JSON, created_at, updated_at

answers
  id, session_id FK, question_id, attempt INT, audio_ref, transcript,
  extracted_value JSON, evidence_quote, extraction_source: gemini|evon|demo-parser|worker,
  needs_confirmation BOOL, confirmed BOOL, created_at

visits
  id UUID PK, session_id FK, visit_code, language_code,
  patient_age INT NULL, reported_symptoms JSON, negated_symptoms JSON,
  follow_up_phrase TEXT NULL, follow_up_date DATE NULL, notes TEXT NULL,
  status: draft|confirmed|deleted, version INT, updated_at, deleted_at NULL

field_evidence
  id, visit_id FK, field_name, evidence_quote, answer_id FK, source='prisma-transcript'

follow_ups
  id, visit_id FK, due_date, status: pending|completed|missed, created_at, updated_at

audit_events
  id, session_id, visit_id, occurred_at,
  action: created|updated|corrected|confirmed|deleted|follow_up_completed|follow_up_missed|sync_failed|sync_completed,
  summary, before JSON, after JSON, actor='Demo worker (synthetic)'
```

---

## 8. API (summary — full contracts in §21)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service + provider config status |
| POST | `/api/calls/start` | `{language_code}` → `session_id`, first prompt (text + audio URL) |
| POST | `/api/calls/{id}/answer` | audio **or** text **or** `dtmf` digit for current question → transcript, value, evidence, readback, options |
| POST | `/api/calls/{id}/action` | `{action: confirm|correct|repeat|skip, field?}` → next prompt |
| POST | `/api/calls/{id}/finalize` | Save visit, create follow-up, audit |
| GET | `/api/calls/{id}` | Session state |
| GET | `/api/visits` · `/api/visits/{id}` | Register + evidence + audit |
| PUT | `/api/visits/{id}` | Versioned upsert `{version}` → 409 on stale |
| DELETE | `/api/visits/{id}` | Soft delete |
| GET | `/api/followups` | Grouped: overdue / today / upcoming / completed / missed |
| PATCH | `/api/followups/{id}` | Mark completed/missed |
| GET | `/api/audit` | Audit events |
| POST | `/api/tts` | Timbre proxy |
| POST | `/api/sync` | Batch upload offline drafts (idempotent by id) |

Provider keys stay on the backend only.

---

## 9. Extraction Rules

- Extract **one field per call**; never "summarize the visit".
- Prompt input: question, expected field, transcript, language. Output strict JSON:
  `{ "value": ..., "evidence_quote": "...", "needs_confirmation": bool, "reason": "..." }`
- No inference of unstated facts. Unclear → `value: null, needs_confirmation: true`.
- Symptoms: split reported vs negated ("no cough"), keep qualifiers ("mild"). No diagnosis.
- Spoken self-corrections ("120 by 80, sorry 110 by 70") → take the last value, quote both.
- Dates: store the phrase ("Friday") **and** a backend-computed candidate ISO date relative to the visit date (next occurrence). Read back the full date ("Friday, 13 November") and require confirmation. Never save an unconfirmed date. *(Updated — see §19 F6.)*
- Temperature with no unit → null + ask. Never assume Fahrenheit.
- Local parser: never guess a name from the first word; label as `demo-parser`.
- DTMF digits bypass the LLM entirely.

---

## 10. Sync Rules (fixes known bugs)

- Every record has `id`, `version`, `updated_at`.
- Mark `synced` **only** when server echoes the same `version` it stored — not merely when the id exists (current bug).
- Stale write → 409 → keep local as `conflict`, show to user.
- Failed sync stays visibly `pending`; auto-retry on `online` event + manual **Sync now**.
- Audit events persist even after soft delete.

---

## 11. Frontend

### Screens

1. **Home** — big *Start visit call*, language chips, follow-ups due today, sync badge.
2. **Call Session** — question, big mic, waveform, on-screen keypad (1/2/3/9), transcript, detected value, evidence.
3. **Correction** — original value + evidence → new answer → updated value.
4. **Final Review** — compact summary with evidence; Save / Correct / Restart.
5. **Saved** — confirmation, sync status, follow-up created, simulated SMS.
6. **Register** — visits with status + sync chips, evidence viewer.
7. **Follow-ups** — overdue / today / upcoming / done / missed.
8. **Audit Trail** — before → after diffs.
9. **Supervisor** (desktop) — today's visits, pending/failed sync, unresolved fields, recent audit.

### Design system

- Light UI, one accent (deep teal `#0F766E`), neutral surfaces, large type (≥ 18 px body on call screen).
- Status: green saved/synced · amber needs confirmation · red failed/overdue · grey pending/offline.
- One primary action per screen, ≥ 56 px touch targets, bottom nav on mobile.
- Feels like a phone dialer, not a hospital dashboard.

---

## 12. Repository Structure (superseded by §22)

```
gnani_ai_internship/
├── README.md                     # SunoCare overview, setup, eval results, demo link
├── docs/
│   ├── SUNOCARE_REWORK.md        # this file
│   └── EVALUATION.md
├── frontend/
│   ├── index.html                # <title>SunoCare</title>
│   ├── public/sw.js
│   └── src/
│       ├── App.tsx  api.ts  storage.ts  types.ts  styles.css
│       ├── components/
│       │   CallSession.tsx  LanguageSelector.tsx  Keypad.tsx  QuestionCard.tsx
│       │   TranscriptEvidence.tsx  CorrectionFlow.tsx  ReviewSummary.tsx
│       │   SavedScreen.tsx  VisitRegister.tsx  FollowUps.tsx  AuditTrail.tsx
│       │   SyncStatus.tsx  SupervisorDashboard.tsx
│       └── hooks/
│           useCallSession.ts  useSpeechRecorder.ts  useOfflineQueue.ts  useTTS.ts
└── backend/
    ├── requirements.txt  .env.example
    ├── app/
    │   main.py  db.py  schemas.py  call_flow.py  questions.py
    │   providers/  prisma.py  timbre.py  gemini.py  evon.py  demo_parser.py
    │   services/   extraction.py  validation.py  audit.py  sync.py  followups.py
    └── tests/
        test_call_flow.py  test_extraction.py  test_validation.py  test_sync.py
```

`.env.example`
```
GNANI_API_KEY=
GNANI_PRISMA_URL=
GNANI_TIMBRE_URL=
GEMINI_API_KEY=
EVON_URL=
DATABASE_URL=sqlite:///./sunocare.db
CORS_ORIGINS=http://localhost:5173
```

---

## 13. Development Workflow

### Branching
- `main` = always demo-able. Work on `feat/<milestone>` branches → PR → merge.
- Commit style: `feat:`, `fix:`, `docs:`, `test:`.

### Local run
```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload --port 8000
# frontend
cd frontend && npm install && npm run dev
```

### Definition of done (per feature)
- Works with real Prisma/Timbre **and** with provider failure (clear error, nothing lost).
- Unit test added; `pytest` passes; `npm run build` passes.
- No "SwarSathi" left in user-facing text (`rg -i swarsathi`).

### Agent workflow (Perplexity Computer / Codex)
1. Give the agent this file + one milestone at a time.
2. Ask for: plan → code → tests → short changelog.
3. Review diff, run locally, then merge.
4. Never ask for "rebuild everything" in one prompt.

---

## 14. Milestones (deadline 10 Nov 2026, 11:59 PM IST)

| Day | Milestone | Output |
|---|---|---|
| Nov 7 | **M0 Rename + M1 Call flow** | SunoCare rename; state machine; per-answer Prisma; Timbre prompts; keypad |
| Nov 8 | **M2 Evidence & correction + M3 Sync** | Evidence UI, targeted correction, audit; versioned sync fix, offline drafts |
| Nov 9 | **M4 UI polish + follow-ups + M5 Eval** | New design, follow-ups, supervisor view; 20–30 synthetic tests; record demo, **publish post** |
| Nov 10 | **Submit** | README, form, post links; buffer for fixes |

Priority if short on time: call flow → Prisma → Timbre read-back → evidence → correction → sync → follow-ups → UI polish → supervisor → eval → demo.

---

## 15. Evaluation (`docs/EVALUATION.md`)

20–30 synthetic recordings covering: clear speech, noise, Malayalam/Hindi–English code-mixing, negation, spoken corrections, missing units, ambiguous dates, irrelevant chatter, duplicate values, network failure.

| Metric | How |
|---|---|
| Field accuracy | vs hand-written answer key |
| Hallucinated fields | values not in transcript |
| Correctly-flagged ambiguity | needs_confirmation when it should |
| Correction success | targeted fix applied |
| Latency | answer stop → read-back |
| Offline recovery | drafts survive reload and sync |
| Sync correctness | pending edits never falsely `synced` |

Report real counts, including failures.

---

## 16. Demo Video (45–60 s)

1. Hook: "No app. No typing. No mobile data. Just call and speak."
2. Start call → Malayalam.
3. Answer age + symptoms → transcript + evidence highlight.
4. Follow-up "Friday" → correct to "Monday" (the hero moment).
5. Timbre final read-back → press 1 → Saved.
6. Offline draft "Saved on device — transcription when online" → reconnect → synced.
7. Follow-up appears in list. End card: **SunoCare — Listen. Confirm. Care.**

---

## 17. Submission Checklist

- [ ] Uses Gnani Prisma + Timbre meaningfully
- [ ] Working demo video
- [ ] README: problem, solution, architecture, Gnani tech, eval results, limitations
- [ ] Public LinkedIn/X post live **before** submission with required hashtags + Gnani tag
- [ ] No real personal data anywhere
- [ ] No paid/bot engagement
- [ ] Submitted before 10 Nov 2026, 11:59 PM IST

## 18. Limitations (state openly)

Prototype, synthetic data, no auth, demo actor labels, simulated SMS, web call simulator instead of real telephony, cloud STT/TTS need connectivity, not a replacement for government health systems.

---
---

# PART B — Full Build Specification

Sections 19–28 were added after a review of sections 1–18. They fill gaps in the original workflow and contain enough detail for a full build. **If anything in sections 1–18 conflicts with Part B, Part B wins.**

## 19. Flaws Found in the Original Workflow & Fixes

| # | Flaw | Why it breaks | Fix |
|---|---|---|---|
| F1 | **Visit codes come from nowhere.** No table backs `4821`. | Unknown/mistyped codes silently create junk visits. | Add `visit_cards` seed table (synthetic). Validate code; on miss: *"Code not found. Say it again or press 0 to start a new unlinked visit."* Read back code digit-by-digit. |
| F2 | **Greeting before language is chosen** — which language does Timbre speak? | First prompt can't be in the user's language. | Greeting is a short multilingual pre-recorded clip (each option spoken in its own language). Remember last language on device; offer "press 1 to continue in Malayalam". |
| F3 | **Offline mode had no guided flow.** Timbre is cloud-only, so prompts couldn't play offline. | Offline = back to unstructured notes. | Generate all fixed prompts at build time (`scripts/generate_prompts.py` → `frontend/public/prompts/{lang}/{prompt_id}.mp3`), cache via service worker. Offline flow runs the **same question state machine on the client** (shared `questions.json`), stores per-question audio, then `POST /api/sync/drafts` on reconnect → visit status `needs_review`. |
| F4 | **Spoken "one"/"yes"/"ശരി"/"haan" for confirm** were sent through an LLM. | Slow, costly, error-prone for 1-word replies. | Deterministic **intent matcher** (`services/intents.py`) with per-language keyword lists for confirm/correct/repeat/skip/yes/no + digit words. LLM only for open fields (age-in-words fallback, symptoms, date phrases, notes). |
| F5 | **No retry limit.** Bad audio loops forever. | Worker gives up. | Max 2 attempts per field → 3rd time offer keypad entry or "press 9 to mark unresolved". Unresolved fields become `needs_review` and show up in supervisor's view. |
| F6 | **"Friday" never becomes a date** → follow-up can't be grouped as today/overdue. | Follow-ups list breaks. | Backend resolves candidate date relative to the visit date; read back the full date; worker confirms. |
| F7 | **`visit_done = no`** path undefined. | Flow asks age/symptoms for a visit that never happened. | Branch: ask reason (house locked / patient away / refused / other) → offer reschedule date → save as `visit_status=not_completed` with follow-up. |
| F8 | **Prompts are English text.** Malayalam/Hindi/Tamil translation unspecified. | Runtime machine translation is unreliable. | Hand-authored prompt strings in `shared/i18n/{lang}.json`. Number/date read-back via `services/speakable.py` (per-language number words). Mark untested languages as "beta" in the UI. |
| F9 | **Prisma clip limit not enforced.** | Long answers fail. | Recorder auto-stops at 25 s with visible countdown; VAD silence auto-stop after 2 s silence. |
| F10 | **Duplicate submissions** on flaky network. | Same answer saved twice / state skips a question. | Client generates `answer_id` (UUID); `/answer` is idempotent on `(session_id, answer_id)`. |
| F11 | **Session abandoned mid-call** (call drop, tab closed). | Partial data lost or orphaned. | Sessions persisted after each step; `GET /api/calls/active` lets the worker resume within 2 hours. After that → `abandoned`; partial answers kept for review. |
| F12 | **Timbre latency/cost on every prompt.** | Slow call experience. | Fixed prompts are pre-generated; dynamic read-backs cached by `sha256(lang+voice+text)` in `backend/cache/tts/`. |
| F13 | **No role separation** between worker and supervisor. | Demo is confusing. | Simple role toggle (Worker / Supervisor) stored locally; clearly labelled "demo role — no authentication". |
| F14 | **Audio retention** unspecified. | Privacy risk even with synthetic data. | Store audio under `backend/storage/audio/{session}/{answer}.wav`; delete it 7 days after confirmation (configurable); evidence quote text is kept. |
| F15 | **No provider mocks.** | Tests and demo depend on live APIs and credits. | `PROVIDER_MODE=live|mock` env var. Mock Prisma returns fixture transcripts keyed by audio filename; mock Timbre returns a silent WAV. CI always runs mock. |
| F16 | **Sync conflict case had no UI.** | 409 errors were silently dropped. | `conflict` sync state + a banner offering "Keep mine / Use server". |

## 20. Detailed Architecture

### 20.1 Components & responsibilities

| Layer | Module | Responsibility |
|---|---|---|
| Shared | `shared/questions.json` | Single source of truth for question IDs, order, branching, answer type, keypad map, retry limit. Imported by frontend and backend. |
| Shared | `shared/i18n/{en,ml,hi,ta}.json` | Prompt text per language. |
| Frontend | `CallEngine` (`hooks/useCallSession.ts`) | Online: thin client over backend session API. Offline: local state machine from `questions.json`. |
| Frontend | `useSpeechRecorder` | Mic → 16 kHz mono WAV, 25 s cap, silence auto-stop, waveform levels. |
| Frontend | `usePromptPlayer` | Plays cached prompt mp3 or `/api/tts` result; queue + interrupt (barge-in by tapping mic). |
| Frontend | `useOfflineQueue` + `storage.ts` | IndexedDB stores: `drafts`, `answers_audio`, `visits`, `audit`, `outbox`. Retry with backoff on `online` event. |
| Backend | `call_flow.py` | Pure state machine: `next(state, event) -> (state, prompt)`. No I/O, so it's fully unit-testable. |
| Backend | `services/intents.py` | Deterministic keyword/digit matching per language. |
| Backend | `services/extraction.py` | Chooses provider (Gemini → Evon → demo parser), builds per-field prompt, validates JSON. |
| Backend | `services/validation.py` | Pydantic validators: age 0–120, BP `\d{2,3}/\d{2,3}`, temp requires unit, date ISO + not in past for follow-up. |
| Backend | `services/speakable.py` | Converts values into speakable read-back text per language. |
| Backend | `services/dates.py` | Relative-date resolution ("Friday", "next Monday", "naale", "kal") → candidate ISO date. |
| Backend | `services/sync.py` | Versioned upsert, conflict detection, draft batch processing. |
| Backend | `services/followups.py` | Create/group/update follow-ups; compute overdue nightly-on-read. |
| Backend | `services/audit.py` | Append-only audit with before/after JSON. |
| Backend | `providers/*` | HTTP adapters with timeouts (STT 20 s, TTS 10 s, LLM 15 s), 1 retry, typed errors. |

### 20.2 Sequence — online answer

```
Worker      Frontend               Backend                    Prisma   LLM    Timbre
  │ speak     │                       │                          │        │       │
  │──────────▶│ record WAV (≤25s)     │                          │        │       │
  │           │ POST /answer(audio,   │                          │        │       │
  │           │   answer_id)─────────▶│ idempotency check        │        │       │
  │           │                       │──── transcribe ─────────▶│        │       │
  │           │                       │◀─── transcript ──────────│        │       │
  │           │                       │ intents.match()? ──yes──▶ value   │       │
  │           │                       │   └─no──▶ extract ───────────────▶│       │
  │           │                       │◀──────────── JSON ────────────────│       │
  │           │                       │ validate → speakable → tts(cache)────────▶│
  │           │◀── {transcript,value, │◀───────────────────────────────── audio ──│
  │           │    evidence,readback} │                                           │
  │◀── play readback + show evidence ─│                                           │
  │ press 1   │ POST /action confirm ▶│ state→next question, audit                │
```

### 20.3 Sequence — offline draft

```
No signal → client CallEngine runs questions.json locally
  → plays cached prompt mp3s → records one WAV per question → IndexedDB(drafts)
  → shows "Saved on device — will process when online"
Reconnect → POST /api/sync/drafts (multipart, draft_id idempotent)
  → backend transcribes + extracts each answer → visit.status = needs_review
  → worker sees "1 visit needs your review" → per-field confirm/correct → confirmed
```

### 20.4 Error handling matrix

| Failure | User sees / hears | System does |
|---|---|---|
| Prisma timeout/5xx | "Couldn't hear that clearly. Saved on this device." | Keep audio, retry once, else queue as draft |
| Empty transcript | "I didn't catch that. Please say it again." | Counts as an attempt (F5) |
| LLM invalid JSON | Falls back to next provider → demo parser → `needs_confirmation` | Log `extraction_source` |
| Validation fail (age 300) | "Age 300 seems wrong. Please say it again." | No save |
| Timbre fail | Text shown on screen + cached generic beep prompt | Continue flow |
| Backend unreachable | Switch to offline draft mode automatically | Outbox retry |
| 409 conflict | Conflict banner | Keep both versions until resolved |

## 21. API Contracts

```jsonc
// POST /api/calls/start
{ "language_code": "ml-IN", "visit_code": "4821" }
→ 200 { "session_id": "uuid", "state": "Q_VISIT_DONE",
        "prompt": { "id": "visit_done", "text": "...", "audio_url": "/prompts/ml/visit_done.mp3" },
        "expects": { "type": "boolean", "keypad": {"1": true, "2": false} },
        "visit_card": { "code": "4821", "label": "Synthetic household #21" } }
→ 404 { "error": "visit_code_not_found" }

// POST /api/calls/{id}/answer   (multipart: audio | form: text | form: dtmf)
{ "answer_id": "uuid", "question_id": "age", "dtmf": null }
→ 200 { "transcript": "ഇരുപത്തിയാറ് വയസ്സ്", "value": 26,
        "evidence_quote": "ഇരുപത്തിയാറ്", "extraction_source": "intent|gemini|evon|demo-parser",
        "needs_confirmation": true, "attempt": 1,
        "readback": { "text": "Age 26. Press 1 to confirm, 2 to correct.", "audio_url": "/api/tts/cache/ab12.wav" },
        "options": ["confirm","correct","repeat"] }

// POST /api/calls/{id}/action
{ "action": "confirm|correct|repeat|skip|unresolved", "field": "follow_up_date" }
→ 200 { "state": "Q_FOLLOWUP_NEEDED", "prompt": {...} }

// POST /api/calls/{id}/finalize
→ 200 { "visit": {..., "version": 1}, "follow_up": {...}, "sms_preview": "SunoCare: visit 4821 saved..." }

// PUT /api/visits/{id}
{ "version": 3, "patch": {...} } → 200 {version: 4} | 409 {server_version: 4, server_visit: {...}}

// POST /api/sync/drafts  (multipart: draft.json + audio files)
→ 200 { "draft_id": "uuid", "visit_id": "uuid", "status": "needs_review" }

// GET /api/calls/active?device_id=... → resumable session or 204
// GET /api/health → { prisma: "ok|missing|error", timbre: ..., gemini: ..., evon: ..., mode: "live|mock" }
```

## 22. Final Repository Structure

```
gnani_ai_internship/
├── README.md
├── docs/  SUNOCARE_REWORK.md  EVALUATION.md  ARCHITECTURE.png (export of §20)
├── shared/
│   ├── questions.json
│   └── i18n/ en.json  ml.json  hi.json  ta.json
├── scripts/
│   ├── generate_prompts.py      # Timbre → frontend/public/prompts/{lang}/*.mp3
│   ├── seed.py                  # synthetic visit_cards + demo visits
│   └── run_eval.py              # eval/cases → results table
├── eval/  cases.jsonl  audio/  expected/
├── frontend/
│   ├── index.html  vite.config.ts  package.json
│   ├── public/  sw.js  manifest.webmanifest  prompts/
│   └── src/
│       ├── main.tsx  App.tsx  router.tsx  api.ts  storage.ts  types.ts
│       ├── engine/  callMachine.ts  questions.ts      # offline state machine
│       ├── hooks/   useCallSession.ts  useSpeechRecorder.ts  usePromptPlayer.ts
│       │            useOfflineQueue.ts  useOnline.ts  useRole.ts
│       ├── screens/ Home.tsx  Call.tsx  Correction.tsx  FinalReview.tsx  Saved.tsx
│       │            Register.tsx  VisitDetail.tsx  FollowUps.tsx  Audit.tsx
│       │            NeedsReview.tsx  Supervisor.tsx
│       ├── components/ BigMicButton  Waveform  Keypad  QuestionCard  EvidenceChip
│       │            FieldRow  StatusChip  SyncBanner  ConflictBanner  BottomNav  Toast
│       └── styles/  tokens.css  base.css
└── backend/
    ├── requirements.txt  .env.example  pytest.ini
    ├── app/
    │   ├── main.py  config.py  db.py  models.py  schemas.py
    │   ├── call_flow.py
    │   ├── routers/  calls.py  visits.py  followups.py  audit.py  sync.py  tts.py  health.py
    │   ├── services/ intents.py  extraction.py  validation.py  speakable.py  dates.py
    │   │             sync.py  followups.py  audit.py  audio_store.py
    │   └── providers/ base.py  prisma.py  timbre.py  gemini.py  evon.py  demo_parser.py  mock.py
    ├── storage/audio/   cache/tts/      # gitignored
    └── tests/ test_call_flow.py  test_intents.py  test_extraction.py  test_dates.py
               test_validation.py  test_sync.py  test_api.py  fixtures/
```

**Migration from current code:** `providers/evon.py`, which currently mixes Gemini, Evon and the demo parser, gets split into `gemini.py`, `evon.py` and `demo_parser.py`, with selection moved to `services/extraction.py`. `App.tsx` (about 1,000 lines) gets split into `screens/` and `components/`. `storage.ts` keeps IndexedDB, with new stores added. `/api/visits/process` stays temporarily for the free-note mode and is removed after M3.

## 23. `questions.json` (shape)

```json
{
  "version": 1,
  "max_attempts": 2,
  "flow": [
    { "id": "visit_done", "type": "boolean", "keypad": {"1": true, "2": false},
      "next": { "true": "age", "false": "not_done_reason" } },
    { "id": "not_done_reason", "type": "enum",
      "options": {"1":"house_locked","2":"patient_away","3":"refused","4":"other"},
      "next": "followup_date" },
    { "id": "age", "type": "integer", "min": 0, "max": 120, "keypad": "digits", "next": "symptoms" },
    { "id": "symptoms", "type": "symptoms", "optional": true, "next": "followup_needed" },
    { "id": "followup_needed", "type": "boolean", "keypad": {"1": true, "2": false},
      "next": { "true": "followup_date", "false": "notes" } },
    { "id": "followup_date", "type": "date_phrase", "next": "notes" },
    { "id": "notes", "type": "free_text", "optional": true, "next": "FINAL_REVIEW" }
  ]
}
```

## 24. State Machine Rules

- States: `LANGUAGE → VISIT_CODE → <question ids…> → FINAL_REVIEW → SAVED`; per question sub-states `ASKING → LISTENING → PROCESSING → READBACK`.
- Events: `answer`, `confirm`, `correct`, `repeat`, `skip`, `unresolved`, `timeout`, `restart`.
- `correct` from FINAL_REVIEW → asks "which detail?" (keypad list of answered fields) → re-asks only that field → returns to FINAL_REVIEW, **not** the next question.
- Branch changes: if `followup_needed` is corrected from yes to no, the dependent `followup_date` is dropped and an audit entry is written.
- `skip` is allowed only when `optional: true`.
- `finalize` is blocked while any required field is neither confirmed nor marked `unresolved`.

## 25. UI Specification

- **Tokens:** `--accent #0F766E`, `--ok #15803D`, `--warn #B45309`, `--err #B91C1C`, `--muted #6B7280`, `--bg #F8FAFC`, `--surface #FFFFFF`. Font: Inter / Noto Sans Malayalam / Noto Sans Devanagari / Noto Sans Tamil. Body 18 px on the call screen, 16 px elsewhere.
- **Call screen layout (top → bottom):** progress dots (question 3 of 6) · question text (24 px) · prompt replay button · big mic (96 px) with waveform ring · live status ("Listening… 0:07 / 0:25") · result card (value + evidence chip) · action row [✓ Confirm 1] [✎ Correct 2] [↻ Repeat 3] · collapsible on-screen keypad.
- **Evidence chip:** the quote with the matched words highlighted; tapping it replays the answer audio.
- **Status chips:** Synced · Saved on device · Needs review · Sync failed · Conflict.
- **Accessibility:** every action works by voice, keypad and touch; contrast ≥ 4.5:1; no meaning conveyed by colour alone (each status has an icon and a label); respect `prefers-reduced-motion`.

## 26. Testing Strategy

| Level | What | Tool |
|---|---|---|
| Unit | `call_flow`, `intents`, `dates`, `validation`, `speakable` | pytest |
| Provider | Adapters against recorded fixtures (`PROVIDER_MODE=mock`) | pytest + respx |
| API | Full call: start → answers → correct → finalize | FastAPI TestClient |
| Sync | Stale version → 409; pending never falsely synced; draft idempotency | pytest |
| Frontend | Offline engine transitions, outbox retry | Vitest |
| E2E (manual) | Demo script in Malayalam and English, airplane-mode draft | checklist in `docs/EVALUATION.md` |

## 27. Updated Milestones (with acceptance criteria)

| Day | Milestone | Done when |
|---|---|---|
| Nov 7 | **M0** Rename, split modules, mock mode, `shared/questions.json`, i18n files | `rg -i swarsathi` returns nothing user-facing; `pytest` green in mock mode |
| Nov 7 | **M1** Backend state machine + call routers + intents | Full demo script runs via API in mock mode |
| Nov 8 | **M2** Call screen UI, recorder, prompt player, Prisma/Timbre live | Demo script works by voice in at least one language |
| Nov 8 | **M3** Evidence, correction, branching, retry limits, audit | Friday→Monday correction works; audit shows the before/after diff |
| Nov 9 AM | **M4** Offline engine, cached prompts, draft sync, versioned sync, conflict banner | Airplane-mode visit → reconnect → Needs review → confirmed |
| Nov 9 PM | **M5** Follow-ups, Register, Supervisor, polish, eval run, demo video, **publish post** | EVALUATION.md has real numbers; post is live |
| Nov 10 | Submit + buffer | Checklist in §17 complete |

**Cut list if behind:** Tamil/Hindi → beta labels only · Supervisor screen → reuse Register with filters · conflict banner → "Use server" only · audio replay seek → full-clip replay.

## 28. Workflow Summary (one view)

```
                 ┌──────────── Worker (voice / keypad / touch) ────────────┐
Start ─▶ Language ─▶ Visit code ─(not found)─▶ retry / unlinked visit
                         │
                         ▼
        ┌──── for each question in questions.json ────┐
        │ Ask (cached prompt) → Listen (≤25s)         │
        │ → Prisma → intent match │ LLM extract       │
        │ → validate → read back (Timbre, cached)     │
        │ → 1 confirm │ 2 correct │ 3 repeat │ 9 skip  │
        │   (2 failed attempts → keypad / unresolved) │
        └──────────────────┬──────────────────────────┘
                           ▼
           Final review (correct any field → back here)
                           ▼
        Finalize → visit v1 + follow-up + audit + SMS preview
                           ▼
 Online ─▶ synced ✓        Offline ─▶ outbox → reconnect → process → Needs review → confirm
                           ▼
       Follow-ups (overdue / today / upcoming) → Supervisor view
```
