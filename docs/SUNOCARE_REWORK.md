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
| **Offline draft mode (fallback)** | Nothing at capture time | Audio saved in IndexedDB; transcription & extraction happen after reconnection. |

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

## 8. API

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
- Dates: store phrase ("Friday"); convert to ISO only if explicit; otherwise confirm.
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

## 12. Repository Structure

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
