import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDemoVisit, getHealth, getVisits, processAudio, requestTts, saveVisit } from "./api";
import { deleteQueuedVisit, getQueuedVisit, listQueuedVisits, putQueuedVisit } from "./storage";
import type { ProviderHealth, QueuedVisit, VisitFields, VisitRecord } from "./types";

const EMPTY_FIELDS: VisitFields = {
  patient_name: "",
  age: null,
  vitals: { blood_pressure: "", temperature_f: null },
  symptoms: [],
  follow_up_date: "",
  follow_up_phrase: "",
  notes: "",
};

const languages = [
  { code: "hi-IN", label: "Hindi / Hinglish" },
  { code: "ta-IN", label: "Tamil / Tanglish" },
  { code: "kn-IN", label: "Kannada" },
  { code: "te-IN", label: "Telugu" },
  { code: "mr-IN", label: "Marathi" },
  { code: "bn-IN", label: "Bengali" },
];

function formatDate(date: string): string {
  if (!date) return "Today";
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(date));
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function sourceLabel(source: string): string {
  if (source === "evon-v3.3") return "Evon v3.3";
  if (source === "synthetic-demo") return "Synthetic sample";
  if (source === "demo-parser") return "Demo extractor";
  return source;
}

function initials(name: string | null): string {
  if (!name) return "?";
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

export default function App() {
  const [queue, setQueue] = useState<QueuedVisit[]>([]);
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [health, setHealth] = useState<ProviderHealth | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [language, setLanguage] = useState("hi-IN");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [ttsUrl, setTtsUrl] = useState<string | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const inFlightRef = useRef(new Set<string>());

  const active = useMemo(() => queue.find((item) => item.id === activeId) ?? null, [queue, activeId]);
  const pendingCount = queue.filter((item) => item.state !== "ready").length;

  const refreshLocal = useCallback(async () => {
    const items = await listQueuedVisits();
    setQueue(items);
    if (!activeId && items.length) setActiveId(items[0].id);
  }, [activeId]);

  const refreshServer = useCallback(async () => {
    try {
      const [records, providerHealth] = await Promise.all([getVisits(), getHealth()]);
      setVisits(records);
      setHealth(providerHealth);
    } catch {
      // Local capture and review remain available when the backend is unreachable.
    }
  }, []);

  const updateQueued = useCallback(async (id: string, patch: Partial<QueuedVisit>) => {
    const current = await getQueuedVisit(id);
    if (!current) return;
    await putQueuedVisit({ ...current, ...patch });
    setQueue(await listQueuedVisits());
  }, []);

  const processQueued = useCallback(async (id: string) => {
    if (inFlightRef.current.has(id) || !navigator.onLine) return;
    const item = await getQueuedVisit(id);
    if (!item?.audio) return;
    inFlightRef.current.add(id);
    await updateQueued(id, { state: "processing", error: undefined });
    try {
      const result = await processAudio(item.audio, item.language, id);
      await putQueuedVisit({ ...item, ...result, state: "ready", audio: item.audio, error: undefined });
      setQueue(await listQueuedVisits());
      setActiveId(id);
      setMessage("Transcript ready. Review every field before saving.");
      await refreshServer();
    } catch (error) {
      await updateQueued(id, { state: navigator.onLine ? "error" : "waiting", error: getErrorMessage(error) });
    } finally {
      inFlightRef.current.delete(id);
    }
  }, [refreshServer, updateQueued]);

  useEffect(() => {
    let cancelled = false;
    void listQueuedVisits().then((items) => {
      if (cancelled) return;
      const recovered = items.map((item) => item.state === "processing" ? { ...item, state: "waiting" as const } : item);
      setQueue(recovered);
      if (recovered.some((item, index) => item !== items[index])) {
        void Promise.all(recovered.map((item) => putQueuedVisit(item)));
      }
      if (recovered.length) setActiveId(recovered[0].id);
      setLoadingPage(false);
    }).catch((error: unknown) => {
      setMessage(getErrorMessage(error));
      setLoadingPage(false);
    });
    void refreshServer();
    const onlineHandler = () => setOnline(true);
    const offlineHandler = () => setOnline(false);
    window.addEventListener("online", onlineHandler);
    window.addEventListener("offline", offlineHandler);
    return () => {
      cancelled = true;
      window.removeEventListener("online", onlineHandler);
      window.removeEventListener("offline", offlineHandler);
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [refreshServer]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  useEffect(() => {
    return () => {
      if (ttsUrl) URL.revokeObjectURL(ttsUrl);
    };
  }, [ttsUrl]);

  async function beginRecording() {
    setMessage("");
    setConfirmation("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMessage("This browser cannot record audio. Open SwarSathi in a recent mobile browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const audio = new Blob(chunksRef.current, { type: mimeType });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        void storeRecording(audio);
      };
      recorder.start();
      setSeconds(0);
      setRecording(true);
    } catch (error) {
      setMessage(getErrorMessage(error) || "Microphone permission is needed to record a visit.");
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
  }

  async function storeRecording(audio: Blob) {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const item: QueuedVisit = {
      id,
      created_at: now,
      transcript: "",
      language,
      extraction_source: "pending",
      visit: structuredClone(EMPTY_FIELDS),
      state: "waiting",
      audio,
    };
    await putQueuedVisit(item);
    await refreshLocal();
    setActiveId(id);
    setMessage(online ? "Recording saved on this device. Sending it for transcription…" : "Recording saved on this device. It will sync when you are online.");
    if (online) void processQueued(id);
  }

  async function loadSample() {
    setBusy(true);
    setMessage("");
    setConfirmation("");
    try {
      const sample = await getDemoVisit();
      await putQueuedVisit(sample);
      await refreshLocal();
      setActiveId(sample.id);
      setMessage("Sample loaded. Edit the fields, then confirm to add it to the register.");
    } catch (error) {
      setMessage(getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function syncPending() {
    const items = await listQueuedVisits();
    const pending = items.filter((item) => item.audio && item.state !== "processing");
    if (!pending.length) {
      setMessage("There are no recorded visits waiting to sync.");
      return;
    }
    setMessage(`Syncing ${pending.length} recorded visit${pending.length === 1 ? "" : "s"}…`);
    await Promise.all(pending.map((item) => processQueued(item.id)));
  }

  async function saveCurrentVisit() {
    if (!active || active.state !== "ready") return;
    setSaving(true);
    setMessage("");
    setTtsUrl(null);
    try {
      const saved = await saveVisit(active);
      await deleteQueuedVisit(active.id);
      setQueue(await listQueuedVisits());
      setVisits((current) => [saved, ...current.filter((visit) => visit.id !== saved.id)]);
      setActiveId(null);
      const name = active.visit.patient_name?.trim() || "the patient";
      const followUp = active.visit.follow_up_phrase || active.visit.follow_up_date;
      const summary = followUp
        ? `Visit recorded for ${name}. Follow-up: ${followUp}.`
        : `Visit recorded for ${name}.`;
      setConfirmation(summary);
      setMessage("Visit saved to the register. The local recording has been removed from the sync queue.");
      try {
        const audio = await requestTts(summary, active.language);
        setTtsUrl(URL.createObjectURL(audio));
      } catch (error) {
        setMessage(`Visit saved. Timbre read-back is unavailable: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      setMessage(`Could not save the visit yet: ${getErrorMessage(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function discardCurrent() {
    if (!active) return;
    await deleteQueuedVisit(active.id);
    const remaining = await listQueuedVisits();
    setQueue(remaining);
    setActiveId(remaining[0]?.id ?? null);
    setMessage("Draft removed from this device.");
  }

  function updateVisit(patch: Partial<VisitFields>) {
    if (!active) return;
    void updateQueued(active.id, { visit: { ...active.visit, ...patch } });
  }

  function updateVitals(patch: Partial<VisitFields["vitals"]>) {
    if (!active) return;
    void updateQueued(active.id, { visit: { ...active.visit, vitals: { ...active.visit.vitals, ...patch } } });
  }

  function updateTranscript(value: string) {
    if (!active) return;
    void updateQueued(active.id, { transcript: value });
  }

  const clock = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SwarSathi home">
          <span className="brand-mark" aria-hidden="true">〰</span>
          <span><strong>SwarSathi</strong><small>ASHA visit register</small></span>
        </a>
        <div className="topbar-right">
          <div className={`connection-pill ${online ? "is-online" : "is-offline"}`}>
            <span className="connection-dot" />{online ? "Online" : "Offline"}
          </div>
          <div className="worker-chip"><span className="worker-avatar">AS</span><span className="worker-name">Demo worker</span></div>
        </div>
      </header>

      <main className="page-wrap">
        <section className="welcome-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> COMMUNITY HEALTH · FIELD NOTES</div>
            <h1>Your visits, <em>heard and organized.</em></h1>
            <p className="welcome-copy">Speak naturally after a home visit. Review the note, make any corrections, and save it to your register.</p>
          </div>
          <div className="today-card">
            <span className="today-icon">✳</span>
            <span><small>TODAY</small><strong>{new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</strong></span>
          </div>
        </section>

        {pendingCount > 0 && (
          <div className={`sync-banner ${online ? "sync-ready" : "sync-waiting"}`}>
            <span className="sync-icon">{online ? "↻" : "◷"}</span>
            <span><strong>{pendingCount} visit{pendingCount === 1 ? "" : "s"} {online ? "ready to sync" : "saved on this device"}</strong><small>{online ? "AI processing starts when you sync." : "Transcription and AI review will run after you reconnect."}</small></span>
            {online && <button className="text-button" onClick={() => void syncPending()}>Sync now <span>→</span></button>}
          </div>
        )}

        {message && <div className="notice" role="status"><span>ℹ</span><p>{message}</p><button aria-label="Dismiss message" onClick={() => setMessage("")}>×</button></div>}
        {confirmation && <div className="success-banner"><span className="success-check">✓</span><div><strong>{confirmation}</strong><small>{ttsUrl ? "Timbre confirmation is ready." : "Saved in your register."}</small></div>{ttsUrl && <audio controls src={ttsUrl} />}</div>}

        <section className="workspace-grid">
          <div className="left-column">
            <section className="card capture-card">
              <div className="card-heading">
                <div><div className="step-label"><span>01</span> NEW VISIT</div><h2>Capture a visit note</h2></div>
                <button className="sample-button" onClick={() => void loadSample()} disabled={busy || recording}><span>✦</span> Try sample note</button>
              </div>

              <label className="field-label language-label" htmlFor="language-select">VOICE LANGUAGE</label>
              <div className="language-select-wrap">
                <select id="language-select" value={language} onChange={(event) => setLanguage(event.target.value)} disabled={recording}>
                  {languages.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                </select>
                <span className="select-chevron">⌄</span>
              </div>

              <div className={`record-panel ${recording ? "recording-now" : ""}`}>
                <div className="record-copy">
                  <span className="record-kicker">{recording ? "LISTENING NOW" : "READY WHEN YOU ARE"}</span>
                  <strong>{recording ? "Tell us about the visit" : "Tap to start recording"}</strong>
                  <span className="record-help">{recording ? "Speak clearly. Tap the button when you’re done." : "Include the patient’s name, observations, and follow-up."}</span>
                </div>
                <div className="record-control-wrap">
                  {recording && <span className="record-timer">{clock}</span>}
                  <button className={`record-button ${recording ? "record-stop" : ""}`} onClick={() => recording ? stopRecording() : void beginRecording()} aria-label={recording ? "Stop recording" : "Start recording"}>
                    {recording ? <span className="stop-square" /> : <span className="mic-icon">🎙</span>}
                  </button>
                </div>
              </div>
              <div className="capture-foot"><span className="secure-icon">♧</span><span>Recordings stay on this device until they sync.</span><span className="duration-note">MAX 2 MIN</span></div>
            </section>

            <section className="card review-card">
              <div className="card-heading review-heading">
                <div><div className="step-label"><span>02</span> CHECK BEFORE SAVING</div><h2>Review visit details</h2></div>
                {active && <span className={`source-badge ${active.extraction_source === "evon-v3.3" ? "source-evon" : ""}`}>{sourceLabel(active.extraction_source)}</span>}
              </div>

              {!active ? (
                <div className="empty-review"><span className="empty-icon">☷</span><strong>No visit selected</strong><p>Record a note or load the sample to start reviewing.</p></div>
              ) : active.state === "processing" ? (
                <div className="processing-state"><span className="spinner" /><div><strong>Preparing your visit note</strong><p>Prisma is transcribing the recording, then the extractor will organize the details.</p></div></div>
              ) : active.state === "waiting" || active.state === "error" ? (
                <div className="pending-state">
                  <div className="pending-art">◷</div>
                  <strong>{active.state === "error" ? "This visit needs another try" : "Waiting for a connection"}</strong>
                  <p>{active.error || "The recording is saved on this device. It will be transcribed after it syncs."}</p>
                  {online && active.audio && <button className="button button-primary button-small" onClick={() => void processQueued(active.id)}>Process recording <span>→</span></button>}
                </div>
              ) : (
                <div className="review-form">
                  <label className="field-label" htmlFor="transcript">TRANSCRIPT <span>EDITABLE</span></label>
                  <textarea id="transcript" className="transcript-box" rows={3} value={active.transcript} onChange={(event) => updateTranscript(event.target.value)} />
                  {active.extraction_source !== "evon-v3.3" && <div className="demo-hint"><span>✦</span> Sample extraction only. Connect Evon to use model-based extraction.</div>}

                  <div className="form-grid">
                    <label className="form-field"><span className="field-label">PATIENT NAME</span><input value={active.visit.patient_name ?? ""} onChange={(event) => updateVisit({ patient_name: event.target.value })} placeholder="Name" /></label>
                    <label className="form-field"><span className="field-label">AGE</span><div className="input-unit"><input type="number" min="0" max="130" value={active.visit.age ?? ""} onChange={(event) => updateVisit({ age: event.target.value ? Number(event.target.value) : null })} placeholder="—" /><span>years</span></div></label>
                    <label className="form-field"><span className="field-label">BLOOD PRESSURE</span><div className="input-unit"><input value={active.visit.vitals?.blood_pressure ?? ""} onChange={(event) => updateVitals({ blood_pressure: event.target.value })} placeholder="— / —" /><span>mmHg</span></div></label>
                    <label className="form-field"><span className="field-label">TEMPERATURE</span><div className="input-unit"><input type="number" step="0.1" value={active.visit.vitals?.temperature_f ?? ""} onChange={(event) => updateVitals({ temperature_f: event.target.value ? Number(event.target.value) : null })} placeholder="—" /><span>°F</span></div></label>
                    <label className="form-field span-two"><span className="field-label">SYMPTOMS <small>SEPARATE WITH COMMAS</small></span><input value={(active.visit.symptoms ?? []).join(", ")} onChange={(event) => updateVisit({ symptoms: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="e.g. mild fever, nausea" /></label>
                    <label className="form-field"><span className="field-label">FOLLOW-UP DATE</span><input type="date" value={active.visit.follow_up_date ?? ""} onChange={(event) => updateVisit({ follow_up_date: event.target.value || null })} /></label>
                    <label className="form-field"><span className="field-label">ORIGINAL DATE PHRASE</span><input value={active.visit.follow_up_phrase ?? ""} onChange={(event) => updateVisit({ follow_up_phrase: event.target.value || null })} placeholder="e.g. Friday" /></label>
                  </div>
                  <div className="review-note"><span>✓</span><p>Please check every field. The app records what was said; it does not diagnose or assign urgency.</p></div>
                  <div className="review-actions">
                    <button className="button button-quiet" onClick={() => void discardCurrent()}>Discard draft</button>
                    <button className="button button-primary" onClick={() => void saveCurrentVisit()} disabled={saving}>{saving ? "Saving…" : "Confirm & save visit"}<span>→</span></button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <aside className="right-column">
            <section className="card register-card">
              <div className="card-heading register-heading"><div><div className="step-label"><span>03</span> YOUR RECORDS</div><h2>Visit register</h2></div><span className="count-badge">{visits.length}</span></div>
              <p className="register-subtitle">Confirmed visits saved on this demo.</p>
              {loadingPage ? <div className="register-empty">Loading register…</div> : visits.length === 0 ? (
                <div className="register-empty"><span className="register-empty-icon">▤</span><strong>Your register is ready</strong><p>Confirmed visits will appear here.</p></div>
              ) : (
                <div className="visit-list">
                  {visits.map((visit) => (
                    <article className="visit-row" key={visit.id}>
                      <div className="patient-initials">{initials(visit.visit.patient_name)}</div>
                      <div className="visit-row-main"><div className="visit-name-line"><strong>{visit.visit.patient_name || "Unnamed patient"}</strong><span>{formatDate(visit.created_at)}</span></div><p>{visit.visit.age ? `${visit.visit.age} years` : "Age not entered"}{visit.visit.symptoms.length ? ` · ${visit.visit.symptoms.slice(0, 2).join(", ")}` : " · No symptoms listed"}</p></div>
                      <span className="saved-check" aria-label="Saved">✓</span>
                    </article>
                  ))}
                </div>
              )}
              <div className="register-footer"><span className="lock-icon">♧</span><span>Synthetic demo entries only</span></div>
            </section>

            <section className="card model-card">
              <div className="model-card-head"><span className="model-spark">✦</span><div><strong>Voice tools</strong><small>Connected services</small></div></div>
              <div className="provider-row"><span className="provider-name"><i className={health?.providers.prisma ? "provider-dot ready" : "provider-dot"} />Prisma transcription</span><span className="provider-status">{health?.providers.prisma ? "Ready" : "Setup needed"}</span></div>
              <div className="provider-row"><span className="provider-name"><i className={health?.providers.evon ? "provider-dot ready" : "provider-dot demo"} />Evon extraction</span><span className="provider-status">{health?.providers.evon ? "Ready" : "Demo mode"}</span></div>
              <div className="provider-row"><span className="provider-name"><i className={health?.providers.timbre ? "provider-dot ready" : "provider-dot"} />Timbre read-back</span><span className="provider-status">{health?.providers.timbre ? "Ready" : "Setup needed"}</span></div>
              <div className="model-footnote">API keys belong in the backend environment file, never in the app.</div>
            </section>

            {queue.length > 0 && (
              <section className="card queue-card">
                <div className="queue-heading"><span>LOCAL QUEUE</span><small>{queue.length} draft{queue.length === 1 ? "" : "s"}</small></div>
                <div className="queue-list">
                  {queue.map((item) => (
                    <button className={`queue-item ${item.id === activeId ? "selected" : ""}`} key={item.id} onClick={() => setActiveId(item.id)}>
                      <span className={`queue-state-dot ${item.state}`} />
                      <span className="queue-item-copy"><strong>{item.visit.patient_name || (item.audio ? "Recorded visit" : "Sample visit")}</strong><small>{item.state === "ready" ? "Ready to review" : item.state === "processing" ? "Processing…" : item.state === "error" ? "Needs retry" : "Waiting to sync"}</small></span>
                      <span className="queue-arrow">›</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </aside>
        </section>

        <footer className="page-footer"><span>Designed for field work, with the worker in control.</span><span>{online ? "Your device is connected" : "Your drafts stay on this device until you reconnect"}</span></footer>
      </main>
    </div>
  );
}
