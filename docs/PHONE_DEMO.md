# Phone setup and hackathon demo

This guide supersedes the simulator-first delivery plan in `SUNOCARE_REWORK.md`. The MVP is one real phone form, Hindi/English prompts, per-answer confirmation and a local supervisor register.

## 1. Confirm Exotel access

Create an account and verify your number through Exotel's dashboard. Before paying, ask support whether they can enable **custom bidirectional Voicebot/AgentStream streaming to your own WSS endpoint**, including DTMF, on a trial/developer account for a student hackathon.

Suggested message to send yourself:

> I am building a student hackathon prototype using synthetic health-visit records. I need an inbound number connected to the Voicebot applet, streaming bidirectional PCM audio and DTMF to my own authenticated WSS server. Can you enable this on a trial/developer account? Please confirm KYC, number availability, pricing and activation requirements before I purchase anything.

Do not assume a generic trial unlocks the applet. [Voicebot onboarding](https://docs.exotel.com/intelligent-voice-agents/connect-your-number-to-your-voicebot) lists KYC as required. The [trial guide](https://docs.exotel.com/business-phone-system/create-a-trial-account) describes registered callers bypassing a PIN and unregistered inbound callers entering one. The claim that all inbound callers must be among ten whitelisted numbers has not been verified for this setup. Use your dashboard's actual number/PIN and account requirements.

Our backend receives calls; it does not place outbound calls. Use the bidirectional **Voicebot** applet, not the unidirectional Stream applet.

## 2. Configure the backend

Keep real values only in `backend/.env`, which is ignored by Git:

```ini
GNANI_API_KEY_ID=<your Gnani key ID>
GEMINI_API_KEY=<your Gemini key>
GEMINI_MODEL=<exact model ID available to your key>
EXOTEL_ACCOUNT_SID=<your Exotel account SID>
TELEPHONY_USER=<a username you choose for this server>
TELEPHONY_PASSWORD=<a strong password you choose for this server>
SUNOCARE_PHONE_NUMBER=<the actual number supplied by Exotel>
```

The WSS username/password authenticate **our gateway**; they are not your Exotel dashboard login or API token. The account SID is checked against each stream's start event. Existing Prisma/Timbre endpoint settings still apply. Restart both Python processes after editing `.env`.

From `backend`, run `.\.venv\Scripts\python.exe check_phone.py --live`. It spends provider credits on synthetic data. The configured model is `gemini-3.5-flash-lite`; synthetic age correction, symptom negation and the Hindi speech-to-extraction check passed with the existing key. Missing Exotel configuration still makes preflight exit with code 1 even when provider checks pass. No demo data silently replaces a failed live model.

## 3. Run the phone gateway and tunnel

Keep the local supervisor API on 8001 and frontend on 5173 running as described in the README. In another terminal, from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.phone_gateway:app --host 127.0.0.1 --port 8002
```

Both Python apps share the configured SQLite database. The gateway exposes only `/health` and the authenticated phone socket; health checks do not verify providers.

After installing/configuring ngrok with your account:

```powershell
ngrok http 8002
```

Put this URL, with your values substituted, into Exotel's Voicebot applet:

```text
wss://<TELEPHONY_USER>:<TELEPHONY_PASSWORD>@<public-domain>/api/telephony/exotel?sample-rate=16000
```

URL-encode reserved characters in the credentials when constructing the URL; keep their original values in `.env`. Enter the URL privately in the provider dashboard, not in Git or a screen recording. Keep the tunnel running, and update Exotel if its domain changes.

Tunnel **8002**, not 8001 or Vite. This keeps the unauthenticated supervisor/legacy write APIs local. [ngrok HTTP tunnels support WebSockets](https://ngrok.com/docs/using-ngrok-with/websockets).

## 4. Map the number to the flow

In App Bazaar, create a flow containing **Voicebot**, enter the WSS URL and attach the flow to your ExoPhone. Check applet access before purchasing a dedicated number. Exotel documents [Basic Auth and sample-rate parameters](https://docs.exotel.com/exotel-agentstream/voicebot-applet).

The implementation handles `start`, `media`, `dtmf`, `mark` and `stop`. It accepts 8, 16 and 24 kHz mono signed 16-bit little-endian PCM, matches playback to the incoming rate and sends 3,200-byte frames. Recording starts after prompt playback acknowledgment. See the [wire protocol](https://developer.exotel.com/docs/agentstream/websocket-protocol).

Use our path `/api/telephony/exotel`, not `/ws/call` from a generic example. HTTP **101** means a successful WebSocket upgrade; **1000** is a normal close code, while **1006** indicates abnormal closure.

## 5. Short demo script

Open `http://127.0.0.1:5173`, dial the configured number from your registered test phone and enter Exotel's PIN if requested. Wait for each prompt.

1. English **4** or Hindi **2**, home visit **1**, visit code **4821**. Other seeded codes: **4822**, **7304**.
2. Completed visit: **1**, then **1** to confirm the read-back.
3. Say **Amina**, press **1** to finish, listen, press **1** to confirm.
4. Say **26 years**, finish and confirm the same way.
5. Say **mild fever, no cough**, finish, hear symptoms present/absent and confirm.
6. Follow-up needed: **1**, then confirm **1**. Speak an explicit future date with day, month and year; finish and confirm.
7. Press **9** to skip optional notes.
8. Final review: **1** reads the summary, **2** offers numbered fields to edit, **3** submits. Demonstrate a correction before submitting if time allows.
9. Hear the saved confirmation. The register should show one new visit and one creation event after its next refresh. Select **Review** to show evidence and the previous answer from the correction.

While answering, **2** repeats the question and clears the current recording. While confirming, **2** replaces the answer and **3** repeats read-back. Optional fields allow **9** to skip. Each recording caps at 25 seconds, then processes automatically.

For another path, mark the visit not completed: it asks for the reason and next visit date instead of patient fields. A real phone demonstration remains unverified until these steps succeed through Exotel.

## 6. Stored data and limits

| Data | Location / timing |
|---|---|
| Call ID, start/end and outcome | SQLite `phone_calls`, on stream start/end |
| Current question and confirmed answers | SQLite `call_sessions`, on each accepted answer/action |
| Raw WAV | `backend/storage/audio/<session>/<answer>.wav`, when recording finishes |
| Transcript, value, quote and audio reference | Session answer after extraction; final visit evidence on submit |
| Replaced answers | `previous_attempts` in evidence |
| Final record + creation event | SQLite `visits` + `audit_events`, atomically on submit |

Duplicate finalization returns the same receipt. These are application audit records, not a tamper-proof audit system. Audio and TTS caches are excluded from Git; automatic retention cleanup and browser audio playback are not implemented.

A dropped call retains saved session data and an incomplete call log, but automatic resumption and partial-session editing in the supervisor are not implemented. Audio still being spoken is in memory; only finished clips reach disk. Failed processing can leave WAV files without structured evidence. Disconnect never automatically submits a visit.

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| No Voicebot applet | Account/KYC and AgentStream access with Exotel |
| No call log | Number-to-flow mapping, public domain, tunnel and gateway |
| Socket rejected | Basic Auth, matching account SID, supported PCM |
| Greeting never plays | Timbre access, server error type, `mark` delivery |
| Answers repeatedly fail | `check_phone.py --live`, Prisma access, Gemini quota/model |
| Call ends after processing failures | Three failed attempts end it without submitting |
| Supervisor empty | API port 8001, shared `DATABASE_PATH`, final submit |

Before recording, complete an actual call with a correction and verify one saved visit, its evidence and completed call status. Hang up on a separate partial call and confirm no final visit is created. Noise/code-mix accuracy needs actual spoken testing; mocks and synthetic TTS do not prove it.
