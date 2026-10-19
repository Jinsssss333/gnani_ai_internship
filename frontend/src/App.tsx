import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { deleteVisit as deleteRemoteVisit, getAuditEvents, getVisits, processAudio, requestTts, saveVisit, syncAuditEvent } from "./api";
import { deleteQueuedVisit, getQueuedVisit, listAuditEvents, listQueuedVisits, listSavedVisits, putAuditEvent, putQueuedVisit, putSavedVisit } from "./storage";
import type { AuditEvent, QueuedVisit, VisitFields, VisitRecord } from "./types";

const EMPTY_FIELDS: VisitFields = {
  patient_name: "",
  age: null,
  vitals: { blood_pressure: "", temperature_f: null },
  symptoms: [],
  follow_up_date: "",
  follow_up_phrase: "",
  notes: "",
};
const MAX_RECORDING_SECONDS = 60;
const PRISMA_SAMPLE_RATE = 16000;

type SampleDialect = "hi-IN" | "ta-IN";
type NotificationKind = "info" | "success" | "warning" | "error";
type AppNotification = { id: string; message: string; created_at: string; kind: NotificationKind; read: boolean };

const CODE_MIX_SAMPLES: Record<SampleDialect, { label: string; transcript: string; patient: string; age: number; symptoms: string[] }> = {
  "hi-IN": {
    label: "Hinglish",
    transcript: "Amina, 26 saal. BP 120 by 80 hai, temperature 98.6 Fahrenheit. Halkasa fever aur nausea hai. Friday ko follow-up rakhna.",
    patient: "Amina",
    age: 26,
    symptoms: ["mild fever", "nausea"],
  },
  "ta-IN": {
    label: "Tanglish",
    transcript: "Amina-ku 26 vayasu. BP 120 by 80, temperature 98.6 Fahrenheit. Mild fever-um nausea-vum irukku. Friday follow-up schedule pannunga.",
    patient: "Amina",
    age: 26,
    symptoms: ["mild fever", "nausea"],
  },
};

function makeCodeMixSample(language: SampleDialect): QueuedVisit {
  const sample = CODE_MIX_SAMPLES[language];
  return {
    id: `sample-${crypto.randomUUID()}`,
    created_at: new Date().toISOString(),
    transcript: sample.transcript,
    language,
    extraction_source: "synthetic-demo",
    visit: {
      patient_name: sample.patient,
      age: sample.age,
      vitals: { blood_pressure: "120/80", temperature_f: 98.6 },
      symptoms: sample.symptoms,
      follow_up_date: null,
      follow_up_phrase: "Friday",
      notes: null,
    },
    state: "ready",
  };
}

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

function notificationKind(message: string): NotificationKind {
  if (/could not|cannot|permission|unavailable|failed|error/i.test(message)) return "error";
  if (/still waiting|saved on this device|will sync|when you.re online|offline|retry/i.test(message)) return "warning";
  if (/complete|synced|ready|saved|updated|removed|loaded|marked/i.test(message)) return "success";
  return "info";
}

function notificationTitle(kind: NotificationKind, message: string): string {
  if (/sync|connection/i.test(message)) return "Sync update";
  if (/recording|transcript/i.test(message)) return "Recording update";
  if (/visit/i.test(message)) return "Visit update";
  return ({ info: "Update", success: "Completed", warning: "Needs attention", error: "Something went wrong" })[kind];
}

function sourceLabel(source: string): string {
  if (source === "gemini" || source === "gemini-argon") return "Gemini";
  if (source === "evon-v3.3") return "Evon v3.3";
  if (source === "synthetic-demo") return "Synthetic sample";
  if (source === "demo-parser") return "Demo extractor";
  return source;
}

function initials(name: string | null): string {
  if (!name) return "?";
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
}

function parseSymptoms(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function toLocalDateInput(date: Date): string {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function dayLabel(date: string): string {
  if (!date) return "Date not set";
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short" }).format(new Date(`${date}T00:00:00`));
}

function auditActionLabel(action: AuditEvent["action"]): string {
  return ({ created: "Visit created", updated: "Visit updated", deleted: "Visit deleted", follow_up_completed: "Follow-up completed", follow_up_missed: "Follow-up marked missed" })[action];
}

async function convertToWav(source: Blob): Promise<Blob> {
  const AudioContextConstructor = window.AudioContext
    ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextConstructor) throw new Error("This browser cannot prepare audio for Prisma.");

  const context = new AudioContextConstructor();
  try {
    const decoded = await context.decodeAudioData(await source.arrayBuffer());
    const sampleCount = Math.ceil(decoded.length * PRISMA_SAMPLE_RATE / decoded.sampleRate);
    const samples = new Float32Array(sampleCount);
    const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index));

    for (let index = 0; index < sampleCount; index += 1) {
      const sourcePosition = index * decoded.sampleRate / PRISMA_SAMPLE_RATE;
      const leftIndex = Math.floor(sourcePosition);
      const rightIndex = Math.min(leftIndex + 1, decoded.length - 1);
      const fraction = sourcePosition - leftIndex;
      let sample = 0;
      for (const channel of channels) {
        sample += channel[leftIndex] * (1 - fraction) + channel[rightIndex] * fraction;
      }
      samples[index] = sample / channels.length;
    }

    const wav = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(wav);
    const writeText = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
    };
    writeText(0, "RIFF");
    view.setUint32(4, wav.byteLength - 8, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, PRISMA_SAMPLE_RATE, true);
    view.setUint32(28, PRISMA_SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let index = 0; index < samples.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return new Blob([wav], { type: "audio/wav" });
  } finally {
    await context.close();
  }
}

export default function App() {
  const [queue, setQueue] = useState<QueuedVisit[]>([]);
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [currentView, setCurrentView] = useState<"dashboard" | "register" | "audit" | "followups">("dashboard");
  const [editingVisit, setEditingVisit] = useState<VisitRecord | null>(null);
  const [editTranscript, setEditTranscript] = useState("");
  const [editFields, setEditFields] = useState<VisitFields>(EMPTY_FIELDS);
  const [editSymptomsText, setEditSymptomsText] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [language, setLanguage] = useState("hi-IN");
  const [sampleDialect, setSampleDialect] = useState<SampleDialect>("hi-IN");
  const [symptomsText, setSymptomsText] = useState("");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [savedNotificationId, setSavedNotificationId] = useState<string | null>(null);
  const [ttsUrl, setTtsUrl] = useState<string | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const inFlightRef = useRef(new Set<string>());
  const queueRef = useRef<QueuedVisit[]>([]);
  const queueWritesRef = useRef(new Map<string, Promise<void>>());
  const processingControllersRef = useRef(new Map<string, AbortController>());
  const syncLockRef = useRef(false);
  const clearingQueueRef = useRef(false);
  const clearedDraftIdsRef = useRef(new Set<string>());

  const active = useMemo(() => queue.find((item) => item.id === activeId) ?? null, [queue, activeId]);
  const activeVisits = visits.filter((visit) => !visit.deleted_at);
  const openFollowUps = activeVisits.filter((visit) => visit.visit.follow_up_date && (visit.visit.follow_up_status ?? "pending") === "pending").sort((a, b) => (a.visit.follow_up_date ?? "").localeCompare(b.visit.follow_up_date ?? ""));
  const todayKey = toLocalDateInput(new Date());
  const dueFollowUps = openFollowUps.filter((visit) => (visit.visit.follow_up_date ?? "") <= todayKey);
  const todayVisitCount = activeVisits.filter((visit) => toLocalDateInput(new Date(visit.created_at)) === todayKey).length;
  const pendingAudioCount = queue.filter((item) => item.state === "waiting" || item.state === "error").length;
  const pendingRegisterCount = visits.filter((visit) => visit.sync_state === "pending").length;
  const pendingAuditCount = auditEvents.filter((event) => event.sync_state === "pending").length;
  const pendingCount = pendingAudioCount + pendingRegisterCount + pendingAuditCount;
  const unreadNotificationCount = notifications.filter((notification) => !notification.read).length;

  function addNotification(message: string): string {
    const notification: AppNotification = {
      id: crypto.randomUUID(),
      message,
      created_at: new Date().toISOString(),
      kind: notificationKind(message),
      read: false,
    };
    setNotifications((current) => [notification, ...current].slice(0, 8));
    return notification.id;
  }

  function dismissNotification(id: string) {
    setNotifications((current) => current.filter((notification) => notification.id !== id));
    if (savedNotificationId === id) {
      setSavedNotificationId(null);
      setTtsUrl(null);
    }
  }

  function clearNotifications() {
    setNotifications([]);
    setSavedNotificationId(null);
    setTtsUrl(null);
  }

  useEffect(() => {
    setSymptomsText(active?.visit.symptoms?.join(", ") ?? "");
  }, [active?.id]);

  function replaceQueue(items: QueuedVisit[]) {
    queueRef.current = items;
    setQueue(items);
  }

  const refreshLocal = useCallback(async () => {
    await Promise.all([...queueWritesRef.current.values()].map((write) => write.catch(() => undefined)));
    const items = await listQueuedVisits();
    replaceQueue(items);
    if (!activeId && items.length) setActiveId(items[0].id);
  }, [activeId]);

  const refreshServer = useCallback(async () => {
    const [localRecords, localEvents] = await Promise.all([listSavedVisits().catch(() => []), listAuditEvents().catch(() => [])]);
    setVisits(localRecords);
    setAuditEvents(localEvents);
    try {
      const [records, remoteEvents] = await Promise.all([getVisits(), getAuditEvents()]);
      const serverIds = new Set(records.map((visit) => visit.id));
      const localWithStatus = localRecords.map((visit) => {
        const updated: VisitRecord = { ...visit, sync_state: serverIds.has(visit.id) ? "synced" : visit.sync_state ?? "pending" };
        if (updated.sync_state !== visit.sync_state) void putSavedVisit(updated);
        return updated;
      });
      const merged = new Map<string, VisitRecord>(records.map((visit) => [visit.id, { ...visit, sync_state: "synced" }]));
      for (const visit of localWithStatus) merged.set(visit.id, visit);
      setVisits([...merged.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)));
      const syncedAuditIds = new Set(remoteEvents.map((event) => event.id));
      const localAudit = localEvents.map((event) => {
        const updated = { ...event, sync_state: syncedAuditIds.has(event.id) ? "synced" as const : event.sync_state ?? "pending" as const };
        if (updated.sync_state !== event.sync_state) void putAuditEvent(updated);
        return updated;
      });
      const mergedEvents = new Map<string, AuditEvent>(remoteEvents.map((event) => [event.id, { ...event, sync_state: "synced" }]));
      localAudit.forEach((event) => mergedEvents.set(event.id, event));
      setAuditEvents([...mergedEvents.values()].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)));
    } catch {
      // Local capture and review remain available when the backend is unreachable.
    }
  }, []);

  async function appendAudit(visit: VisitRecord, action: AuditEvent["action"], summary: string) {
    const event: AuditEvent = {
      id: crypto.randomUUID(),
      visit_id: visit.id,
      occurred_at: new Date().toISOString(),
      action,
      summary,
      actor: "Demo ASHA worker",
      sync_state: "pending",
    };
    await putAuditEvent(event);
    setAuditEvents((current) => [event, ...current.filter((item) => item.id !== event.id)]);
    if (navigator.onLine) {
      try {
        await syncAuditEvent(event);
        const synced = { ...event, sync_state: "synced" as const };
        await putAuditEvent(synced);
        setAuditEvents((current) => current.map((item) => item.id === synced.id ? synced : item));
      } catch {
        // Keep the event locally and retry with the next sync.
      }
    }
  }

  const updateQueued = useCallback(async (id: string, patch: Partial<QueuedVisit>) => {
    const current = queueRef.current.find((item) => item.id === id);
    if (!current) return;
    const updated = { ...current, ...patch };
    replaceQueue(queueRef.current.map((item) => item.id === id ? updated : item));
    const previous = queueWritesRef.current.get(id) ?? Promise.resolve();
    const write = previous.catch(() => undefined).then(() => putQueuedVisit(updated));
    queueWritesRef.current.set(id, write);
    await write;
  }, []);

  const processQueued = useCallback(async (id: string, options: { quiet?: boolean } = {}) => {
    if (clearingQueueRef.current || clearedDraftIdsRef.current.has(id) || inFlightRef.current.has(id) || !navigator.onLine) return;
    const item = await getQueuedVisit(id);
    if (clearingQueueRef.current || clearedDraftIdsRef.current.has(id) || !queueRef.current.some((queued) => queued.id === id) || !item?.audio) return;
    const controller = new AbortController();
    inFlightRef.current.add(id);
    processingControllersRef.current.set(id, controller);
    try {
      await updateQueued(id, { state: "processing", error: undefined });
      const result = await processAudio(item.audio, item.language, id, controller.signal);
      if (clearingQueueRef.current || clearedDraftIdsRef.current.has(id)) return;
      await putQueuedVisit({ ...item, ...result, state: "ready", audio: item.audio, error: undefined });
      if (clearedDraftIdsRef.current.has(id)) {
        await deleteQueuedVisit(id);
        return;
      }
      replaceQueue(await listQueuedVisits());
      setActiveId(id);
      if (!options.quiet) addNotification("Transcript ready. Review every field before saving.");
      await refreshServer();
    } catch (error) {
      if (!clearingQueueRef.current && !clearedDraftIdsRef.current.has(id)) {
        await updateQueued(id, { state: navigator.onLine ? "error" : "waiting", error: getErrorMessage(error) });
      }
    } finally {
      inFlightRef.current.delete(id);
      processingControllersRef.current.delete(id);
    }
  }, [refreshServer, updateQueued]);

  useEffect(() => {
    let cancelled = false;
    void listQueuedVisits().then((items) => {
      if (cancelled) return;
      const recovered = items.map((item) => item.state === "processing" ? { ...item, state: "waiting" as const } : item);
      replaceQueue(recovered);
      if (recovered.some((item, index) => item !== items[index])) {
        void Promise.all(recovered.map((item) => putQueuedVisit(item)));
      }
      if (recovered.length) setActiveId(recovered[0].id);
      setLoadingPage(false);
      if (navigator.onLine) void syncPending({ quiet: true });
    }).catch((error: unknown) => {
      addNotification(getErrorMessage(error));
      setLoadingPage(false);
    });
    void refreshServer();
    const onlineHandler = () => {
      setOnline(true);
      void syncPending({ quiet: true, connectionRestored: true });
    };
    const offlineHandler = () => setOnline(false);
    const foregroundHandler = () => {
      if (document.visibilityState === "visible" && navigator.onLine) void syncPending({ quiet: true });
    };
    window.addEventListener("online", onlineHandler);
    window.addEventListener("offline", offlineHandler);
    document.addEventListener("visibilitychange", foregroundHandler);
    return () => {
      cancelled = true;
      window.removeEventListener("online", onlineHandler);
      window.removeEventListener("offline", offlineHandler);
      document.removeEventListener("visibilitychange", foregroundHandler);
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [refreshServer]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    const maximum = window.setTimeout(() => {
      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
        setRecording(false);
        addNotification("Recording stopped at the 60-second limit. Your note is saved on this device.");
      }
    }, MAX_RECORDING_SECONDS * 1000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(maximum);
    };
  }, [recording]);

  useEffect(() => {
    return () => {
      if (ttsUrl) URL.revokeObjectURL(ttsUrl);
    };
  }, [ttsUrl]);

  async function beginRecording() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      addNotification("This browser cannot record audio. Open SwarSathi in a recent mobile browser.");
      return;
    }
    try {
      const supportedAudio = navigator.mediaDevices.getSupportedConstraints?.() ?? {};
      const audioConstraints: MediaTrackConstraints = {
        ...(supportedAudio.channelCount ? { channelCount: 1 } : {}),
        ...(supportedAudio.noiseSuppression ? { noiseSuppression: true } : {}),
        ...(supportedAudio.echoCancellation ? { echoCancellation: true } : {}),
        ...(supportedAudio.autoGainControl ? { autoGainControl: true } : {}),
      };
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      streamRef.current = stream;
      chunksRef.current = [];
      const supportedMime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
      const recorder = supportedMime
        ? new MediaRecorder(stream, { mimeType: supportedMime })
        : new MediaRecorder(stream);
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
      addNotification(getErrorMessage(error) || "Microphone permission is needed to record a visit.");
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
  }

  async function storeRecording(audio: Blob) {
    setBusy(true);
    try {
      const wav = await convertToWav(audio);
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
        audio: wav,
      };
      await putQueuedVisit(item);
      await refreshLocal();
      setActiveId(id);
      addNotification(online ? "Recording saved on this device. Sending it for transcription…" : "Recording saved on this device. It will sync when you are online.");
      if (online) void processQueued(id);
    } catch (error) {
      addNotification(`Could not prepare the recording: ${getErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadSample() {
    setBusy(true);
    try {
      const existingSample = queueRef.current.find((item) => item.extraction_source === "synthetic-demo" && item.language === sampleDialect);
      if (existingSample) {
        setActiveId(existingSample.id);
        setLanguage(sampleDialect);
        addNotification(`${CODE_MIX_SAMPLES[sampleDialect].label} example is already in your drafts. Reopened it instead of adding another.`);
        return;
      }
      const sample = makeCodeMixSample(sampleDialect);
      await putQueuedVisit(sample);
      await refreshLocal();
      setActiveId(sample.id);
      setLanguage(sampleDialect);
      addNotification(`${CODE_MIX_SAMPLES[sampleDialect].label} example loaded. This synthetic example demonstrates the review flow; record the phrase below to test Gnani transcription.`);
    } catch (error) {
      addNotification(getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function syncPending(options: { quiet?: boolean; connectionRestored?: boolean } = {}) {
    if (syncLockRef.current) return;
    syncLockRef.current = true;
    setSyncing(true);
    try {
      const items = await listQueuedVisits();
      const pendingAudio = items.filter((item) => item.audio && (item.state === "waiting" || item.state === "error"));
      const pendingRegister = (await listSavedVisits()).filter((visit) => visit.sync_state === "pending");
      const pendingAudit = (await listAuditEvents()).filter((event) => event.sync_state === "pending");
      if (!pendingAudio.length && !pendingRegister.length && !pendingAudit.length) {
        if (!options.quiet) addNotification("There are no recorded visits waiting to sync.");
        return;
      }
      if (!options.quiet) addNotification("Syncing saved visits and audit history…");
      await Promise.all(pendingAudio.map((item) => processQueued(item.id, { quiet: options.quiet })));

      let syncedRecords = 0;
      let failedRecords = 0;
      for (const visit of pendingRegister) {
        try {
          const serverRecord = await saveVisit(visit.deleted_at ? { ...visit, deleted_at: null } : visit);
          if (visit.deleted_at) await deleteRemoteVisit(visit.id);
          const synced = { ...serverRecord, deleted_at: visit.deleted_at ?? null, sync_state: "synced" as const };
          await putSavedVisit(synced);
          setVisits((current) => [synced, ...current.filter((item) => item.id !== synced.id)]);
          syncedRecords += 1;
        } catch {
          failedRecords += 1;
        }
      }
      let failedAudit = 0;
      for (const event of pendingAudit) {
        try {
          await syncAuditEvent(event);
          const synced = { ...event, sync_state: "synced" as const };
          await putAuditEvent(synced);
          setAuditEvents((current) => current.map((item) => item.id === synced.id ? synced : item));
        } catch {
          failedAudit += 1;
        }
      }
      await refreshServer();
      const audioWaiting = (await listQueuedVisits()).filter((item) => item.audio && (item.state === "waiting" || item.state === "error")).length;
      if (failedRecords || failedAudit || audioWaiting) {
        const waiting = failedRecords + failedAudit + audioWaiting;
        addNotification(`Sync finished with ${waiting} item${waiting === 1 ? "" : "s"} still waiting. Check the connection and retry.`);
      } else if (!options.quiet) {
        addNotification(`Sync complete. ${syncedRecords} confirmed visit${syncedRecords === 1 ? "" : "s"} added to the register.`);
      } else if (options.connectionRestored) {
        const readyDrafts = (await listQueuedVisits()).filter((item) => item.state === "ready").length;
        addNotification(`Connection restored. Saved register changes synced${readyDrafts ? `; ${readyDrafts} draft${readyDrafts === 1 ? " is" : "s are"} ready to review` : ""}.`);
      }
    } catch (error) {
      if (!options.quiet || options.connectionRestored) addNotification(`Could not sync saved work: ${getErrorMessage(error)}`);
    } finally {
      syncLockRef.current = false;
      setSyncing(false);
    }
  }

  async function saveCurrentVisit() {
    if (!active) return;
    const currentDraft = active;
    setSaving(true);
    setSavedNotificationId(null);
    setTtsUrl(null);
    try {
      await queueWritesRef.current.get(currentDraft.id)?.catch(() => undefined);
      const draft = queueRef.current.find((item) => item.id === currentDraft.id) ?? currentDraft;
      if (draft.state !== "ready") return;
      const localRecord: VisitRecord = {
        id: draft.id,
        created_at: draft.created_at,
        transcript: draft.transcript,
        language: draft.language,
        extraction_source: draft.extraction_source,
        visit: {
          ...draft.visit,
          symptoms: parseSymptoms(draft.visit.symptoms.join(", ")),
          follow_up_status: draft.visit.follow_up_date ? draft.visit.follow_up_status ?? "pending" : undefined,
        },
        sync_state: "pending",
      };
      await putSavedVisit(localRecord);
      await deleteQueuedVisit(draft.id);
      replaceQueue(await listQueuedVisits());
      setVisits((current) => [localRecord, ...current.filter((visit) => visit.id !== localRecord.id)]);
      setActiveId(null);
      await appendAudit(localRecord, "created", `Visit recorded for ${localRecord.visit.patient_name || "unnamed patient"}.`);
      const name = draft.visit.patient_name?.trim() || "the patient";
      const followUp = draft.visit.follow_up_phrase || draft.visit.follow_up_date;
      const summary = followUp
        ? `Visit recorded for ${name}. Follow-up: ${followUp}.`
        : `Visit recorded for ${name}.`;
      const savedNoticeId = addNotification(summary);
      setSavedNotificationId(savedNoticeId);
      if (!navigator.onLine) {
        addNotification("Visit saved on this device. Use Sync now after reconnecting to add it to the shared register.");
        return;
      }

      try {
        const serverRecord = await saveVisit(localRecord);
        const synced = { ...serverRecord, sync_state: "synced" as const };
        await putSavedVisit(synced);
        setVisits((current) => [synced, ...current.filter((visit) => visit.id !== synced.id)]);
        addNotification("Visit saved to this device and synced to the register.");
      } catch (error) {
        addNotification(`Visit is safe on this device and will sync later. ${getErrorMessage(error)}`);
        return;
      }

      try {
        const audio = await requestTts(summary, draft.language);
        setTtsUrl(URL.createObjectURL(audio));
      } catch (error) {
        addNotification(`Visit synced. Timbre read-back is unavailable: ${getErrorMessage(error)}`);
      }
    } catch (error) {
      addNotification(`Could not save the visit on this device: ${getErrorMessage(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function discardCurrent() {
    if (!active) return;
    await queueWritesRef.current.get(active.id)?.catch(() => undefined);
    await deleteQueuedVisit(active.id);
    const remaining = await listQueuedVisits();
    replaceQueue(remaining);
    setActiveId(remaining[0]?.id ?? null);
    addNotification("Draft removed from this device.");
  }

  async function discardAllDrafts() {
    if (!queue.length || busy || recording) return;
    if (!window.confirm(`Remove all ${queue.length} unsaved drafts from this device? Confirmed visits will stay in the register.`)) return;
    clearingQueueRef.current = true;
    queue.forEach((draft) => clearedDraftIdsRef.current.add(draft.id));
    setBusy(true);
    try {
      processingControllersRef.current.forEach((controller) => controller.abort());
      await Promise.all([...queueWritesRef.current.values()].map((write) => write.catch(() => undefined)));
      const drafts = await listQueuedVisits();
      drafts.forEach((draft) => clearedDraftIdsRef.current.add(draft.id));
      await Promise.all(drafts.map((draft) => deleteQueuedVisit(draft.id)));
      replaceQueue(await listQueuedVisits());
      setActiveId(null);
      setSymptomsText("");
      addNotification(`${drafts.length} unsaved draft${drafts.length === 1 ? "" : "s"} cleared from this device. Confirmed visits were kept.`);
    } catch (error) {
      addNotification(`Could not clear the drafts: ${getErrorMessage(error)}`);
    } finally {
      clearingQueueRef.current = false;
      setBusy(false);
    }
  }

  function startEditing(visit: VisitRecord) {
    setEditingVisit(visit);
    setEditTranscript(visit.transcript);
    setEditSymptomsText((visit.visit.symptoms ?? []).join(", "));
    setEditFields({ ...visit.visit, vitals: { ...visit.visit.vitals, blood_pressure: visit.visit.vitals?.blood_pressure ?? "", temperature_f: visit.visit.vitals?.temperature_f ?? null } });
  }

  async function saveRegisterEdit() {
    if (!editingVisit) return;
    setSavingEdit(true);
    const updated: VisitRecord = {
      ...editingVisit,
      transcript: editTranscript,
      visit: {
        ...editFields,
        symptoms: parseSymptoms(editSymptomsText),
        follow_up_status: editFields.follow_up_date ? editFields.follow_up_status ?? "pending" : undefined,
      },
      sync_state: "pending",
      deleted_at: null,
    };
    try {
      await putSavedVisit(updated);
      setVisits((current) => current.map((visit) => visit.id === updated.id ? updated : visit));
      await appendAudit(updated, "updated", "Visit details were edited in the register.");
      if (navigator.onLine) {
        try {
          const remote = await saveVisit(updated);
          const synced = { ...remote, sync_state: "synced" as const };
          await putSavedVisit(synced);
          setVisits((current) => current.map((visit) => visit.id === synced.id ? synced : visit));
          addNotification("Visit updated. The audit trail now includes this change.");
        } catch {
          addNotification("Visit updated on this device. It will sync when the connection is available.");
        }
      } else {
        addNotification("Visit updated on this device. It will sync when the connection is available.");
      }
      setEditingVisit(null);
    } catch (error) {
      addNotification(`Could not update this visit: ${getErrorMessage(error)}`);
    } finally {
      setSavingEdit(false);
    }
  }

  async function removeRegisterVisit(visit: VisitRecord) {
    if (!window.confirm(`Delete the register entry for ${visit.visit.patient_name || "this visit"}? Its audit history will remain.`)) return;
    const deleted: VisitRecord = { ...visit, deleted_at: new Date().toISOString(), sync_state: "pending" };
    try {
      await putSavedVisit(deleted);
      setVisits((current) => current.map((item) => item.id === deleted.id ? deleted : item));
      await appendAudit(deleted, "deleted", `Visit entry for ${visit.visit.patient_name || "unnamed patient"} was deleted from the active register.`);
      if (navigator.onLine && visit.sync_state === "synced") {
        try {
          await deleteRemoteVisit(visit.id);
          const synced = { ...deleted, sync_state: "synced" as const };
          await putSavedVisit(synced);
          setVisits((current) => current.map((item) => item.id === synced.id ? synced : item));
        } catch {
          addNotification("Visit hidden from the active register. Its deletion will sync when possible.");
        }
      } else {
        addNotification("Visit hidden from the active register. Its deletion will sync when possible.");
      }
      setEditingVisit(null);
    } catch (error) {
      addNotification(`Could not delete this visit: ${getErrorMessage(error)}`);
    }
  }

  async function updateFollowUp(visit: VisitRecord, status: "completed" | "missed") {
    const updated: VisitRecord = { ...visit, visit: { ...visit.visit, follow_up_status: status }, sync_state: "pending" };
    await putSavedVisit(updated);
    setVisits((current) => current.map((item) => item.id === updated.id ? updated : item));
    await appendAudit(updated, status === "completed" ? "follow_up_completed" : "follow_up_missed", `Follow-up for ${visit.visit.patient_name || "unnamed patient"} marked ${status}.`);
    if (navigator.onLine) {
      try {
        const remote = await saveVisit(updated);
        const synced = { ...remote, sync_state: "synced" as const };
        await putSavedVisit(synced);
        setVisits((current) => current.map((item) => item.id === synced.id ? synced : item));
        addNotification(`Follow-up marked ${status}.`);
      } catch {
        addNotification("Follow-up status saved locally and will sync later.");
      }
    } else {
      addNotification("Follow-up status saved locally and will sync later.");
    }
  }

  function updateVisit(patch: Partial<VisitFields>) {
    if (!active) return;
    void updateQueued(active.id, { visit: { ...active.visit, ...patch } });
  }

  function updateSymptomsText(value: string) {
    setSymptomsText(value);
    if (!active) return;
    void updateQueued(active.id, {
      visit: {
        ...active.visit,
        symptoms: value.split(",").map((symptom) => symptom.trim()).filter(Boolean),
      },
    });
  }

  function updateVitals(patch: Partial<VisitFields["vitals"]>) {
    if (!active) return;
    void updateQueued(active.id, { visit: { ...active.visit, vitals: { ...active.visit.vitals, ...patch } } });
  }

  function updateTranscript(value: string) {
    if (!active) return;
    void updateQueued(active.id, { transcript: value });
  }

  function renderFollowUpsCard(showAll = false) {
    return (
      <section className="card followup-card" id="followups-card">
        <div className="card-heading register-heading"><div><div className="section-kicker">FOLLOW-THROUGH</div><h2>Upcoming follow-ups</h2></div><span className="count-badge">{openFollowUps.length}</span></div>
        {openFollowUps.length === 0 ? <div className="compact-empty"><span>✓</span><strong>Nothing scheduled</strong>{currentView === "followups" && <button className="inline-link" onClick={() => setCurrentView("register")}>Open visit register →</button>}</div> : <div className="followup-list">{openFollowUps.slice(0, showAll ? openFollowUps.length : 6).map((visit) => {
          const due = (visit.visit.follow_up_date ?? "") <= todayKey;
          return <article className="followup-row" key={visit.id}><span className={`followup-date ${due ? "followup-overdue" : ""}`}>{new Date(`${visit.visit.follow_up_date}T00:00:00`).getDate()}<small>{new Intl.DateTimeFormat("en-IN", { month: "short" }).format(new Date(`${visit.visit.follow_up_date}T00:00:00`))}</small></span><div className="followup-copy"><strong>{visit.visit.patient_name || "Unnamed patient"}</strong><small>{due ? "Due now · " : "Scheduled · "}{dayLabel(visit.visit.follow_up_date || "")}</small><div className="followup-actions"><button onClick={() => void updateFollowUp(visit, "completed")}>Mark done</button><button onClick={() => void updateFollowUp(visit, "missed")}>Mark missed</button></div></div></article>;
        })}</div>}
      </section>
    );
  }

  const clock = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  if (loadingPage) {
    return (
      <div className="loading-splash">
        <span className="brand-mark" aria-hidden="true">〰</span>
        <strong>SwarSathi</strong>
        <div className="loading-bar"><div className="loading-bar-inner" /></div>
      </div>
    );
  }

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
          <details className="notification-center" onToggle={(event) => {
            if (event.currentTarget.open) setNotifications((current) => current.map((notification) => ({ ...notification, read: true })));
          }}>
            <summary className="notification-trigger" aria-label={`Activity notifications${unreadNotificationCount ? `, ${unreadNotificationCount} unread` : ""}`}>
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
              <span>Activity</span>
              {unreadNotificationCount > 0 && <small className="notification-count">{unreadNotificationCount > 9 ? "9+" : unreadNotificationCount}</small>}
            </summary>
            <section className="notification-panel" aria-label="Recent activity">
              <header className="notification-panel-head">
                <div><strong>Activity</strong><small>Updates from this session</small></div>
                {notifications.length > 0 && <button onClick={clearNotifications}>Clear all</button>}
              </header>
              {notifications.length ? <ul className="notification-list">
                {notifications.map((notification) => (
                  <li className={`notification-item notification-${notification.kind}`} key={notification.id}>
                    <span className="notification-kind-icon" aria-hidden="true">{notification.kind === "error" ? "!" : notification.kind === "warning" ? "◷" : notification.kind === "success" ? "✓" : "i"}</span>
                    <div className="notification-copy">
                      <div className="notification-item-head"><strong>{notificationTitle(notification.kind, notification.message)}</strong><time>{new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date(notification.created_at))}</time></div>
                      <p>{notification.message}</p>
                      {notification.id === savedNotificationId && ttsUrl && <audio controls src={ttsUrl} aria-label="Play visit confirmation" />}
                    </div>
                    <button className="notification-dismiss" aria-label="Dismiss notification" onClick={() => dismissNotification(notification.id)}>×</button>
                  </li>
                ))}
              </ul> : <div className="notification-empty"><span>✓</span><strong>All caught up</strong><small>New recording, register, and sync updates will appear here.</small></div>}
            </section>
          </details>
          <span className="demo-mode-pill">SYNTHETIC DEMO</span>
        </div>
      </header>

      <aside className="sidebar" aria-label="Application navigation">
        <button className="sidebar-capture" onClick={() => { setCurrentView("dashboard"); window.setTimeout(() => document.getElementById("capture-card")?.scrollIntoView({ behavior: "smooth", block: "center" }), 80); }}><span>＋</span> New visit</button>
        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          <button className={currentView === "dashboard" ? "sidebar-link sidebar-active" : "sidebar-link"} onClick={() => setCurrentView("dashboard")}><span className="sidebar-icon">⌂</span><span>Dashboard</span></button>
          <button className={currentView === "register" ? "sidebar-link sidebar-active" : "sidebar-link"} onClick={() => setCurrentView("register")}><span className="sidebar-icon">▤</span><span>Visit register</span><small>{activeVisits.length}</small></button>
          <button className={currentView === "audit" ? "sidebar-link sidebar-active" : "sidebar-link"} onClick={() => setCurrentView("audit")}><span className="sidebar-icon">◷</span><span>Audit trail</span><small>{auditEvents.length}</small></button>
          <button className={`sidebar-link sidebar-followups ${currentView === "followups" ? "sidebar-active" : ""}`} onClick={() => setCurrentView("followups")}><span className="sidebar-icon">▦</span><span>Follow-ups</span>{dueFollowUps.length > 0 && <small className="sidebar-badge">{dueFollowUps.length}</small>}</button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-worker"><span className="worker-avatar">MD</span><div><strong>Meena Devi</strong></div><span className="sidebar-chevron">⌄</span></div>
      </aside>

      <main className="page-wrap dashboard-wrap" key={currentView}>
        <section className="welcome-row page-transition">
          <div>
            <h1>{currentView === "dashboard" ? <>Good day, Meena <em>ji.</em></> : currentView === "register" ? <>Your visit <em>register.</em></> : currentView === "audit" ? <>A clear trail of <em>every change.</em></> : <>Follow-ups <em>to complete.</em></>}</h1>
          </div>
          <div className="today-card">
            <span className="today-icon">✳</span>
            <span><small>TODAY</small><strong>{new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date())}</strong></span>
          </div>
        </section>

        {currentView === "dashboard" && <section className="stats-grid" aria-label="Visit summary">
          <article className="stat-card"><span className="stat-icon stat-green">▤</span><div><small>VISITS TODAY</small><strong>{todayVisitCount}</strong><span>confirmed in your register</span></div></article>
          <button className="stat-card stat-card-button" onClick={() => setCurrentView("followups")} aria-label={`Open follow-ups, ${dueFollowUps.length} due and ${openFollowUps.length} scheduled`}><span className="stat-icon stat-amber">◷</span><span className="stat-copy"><small>FOLLOW-UPS DUE</small><strong>{dueFollowUps.length}</strong><span>{openFollowUps.length} scheduled with a date</span></span><span className="stat-open-hint" aria-hidden="true">→</span></button>
          <article className="stat-card"><span className="stat-icon stat-blue">✎</span><div><small>DRAFTS TO REVIEW</small><strong>{queue.length}</strong><span>saved on this device</span></div></article>
          <article className="stat-card"><span className={`stat-icon ${pendingCount ? "stat-amber" : "stat-green"}`}>{pendingCount ? "↻" : "✓"}</span><div><small>REGISTER SYNC</small><strong>{pendingCount ? `${pendingCount} pending` : "Up to date"}</strong><span>{online ? "Device connected" : "Offline · saved locally"}</span></div></article>
        </section>}

        {currentView === "dashboard" && pendingCount > 0 && (
          <div className={`sync-banner ${online ? "sync-ready" : "sync-waiting"}`}>
            <span className="sync-icon">{online ? "↻" : "◷"}</span>
            <span><strong>{pendingCount} item{pendingCount === 1 ? "" : "s"} {online ? "ready to sync" : "saved on this device"}</strong><small>{pendingAudioCount ? "Draft recordings need transcription." : pendingAuditCount ? "Visit history changes are waiting to sync." : "Register changes will sync when connected."}</small></span>
            {online && <button className="text-button" onClick={() => void syncPending()} disabled={syncing}>{syncing ? "Syncing…" : "Sync now →"}</button>}
          </div>
        )}

        {currentView === "followups" && <div className="followups-page">{renderFollowUpsCard(true)}</div>}

        {currentView === "dashboard" && <>
          <div className="dashboard-toolbar"><div><h2>Capture and review</h2></div><button className="button button-primary" onClick={() => document.getElementById("capture-card")?.scrollIntoView({ behavior: "smooth", block: "center" })}>＋ Capture visit</button></div>
          <section className="workspace-grid dashboard-grid">
            <div className="left-column">
              <section className="card capture-card" id="capture-card">
              <div className="card-heading">
                <div><div className="step-label"><span>01</span> NEW VISIT</div><h2>Capture a visit note</h2></div>
                <div className="sample-controls">
                  <select aria-label="Code-mix sample dialect" value={sampleDialect} onChange={(event) => { const selected = event.target.value as SampleDialect; setSampleDialect(selected); setLanguage(selected); }} disabled={busy || recording}>
                    <option value="hi-IN">Hinglish example</option>
                    <option value="ta-IN">Tanglish example</option>
                  </select>
                  <button className="sample-button" onClick={() => void loadSample()} disabled={busy || recording}><span>✦</span> Load example</button>
                </div>
              </div>

              <label className="field-label language-label" htmlFor="language-select">VOICE LANGUAGE</label>
              <div className="language-select-wrap">
                <select id="language-select" value={language} onChange={(event) => { const selected = event.target.value; setLanguage(selected); if (selected === "hi-IN" || selected === "ta-IN") setSampleDialect(selected); }} disabled={recording}>
                  {languages.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                </select>
                <span className="select-chevron">⌄</span>
              </div>

              <div className={`record-panel ${recording ? "recording-now" : ""}`}>
                <div className="record-copy">
                  <span className="record-kicker">{recording ? "LISTENING NOW" : "READY WHEN YOU ARE"}</span>
                  <strong>{recording ? "Tell us about the visit" : "Tap to start recording"}</strong>
                  <span className="record-help">{recording ? "Tap again when you are done." : "Name, vitals, symptoms, follow-up."}</span>
                </div>
                <div className="record-control-wrap">
                  {recording && <span className="record-timer">{clock}</span>}
                  <button className={`record-button ${recording ? "record-stop" : ""}`} onClick={() => recording ? stopRecording() : void beginRecording()} aria-label={recording ? "Stop recording" : "Start recording"} disabled={busy}>
                    {recording ? <span className="stop-square" /> : <span className="mic-icon">🎙</span>}
                  </button>
                </div>
              </div>
              <div className="capture-foot"><span className="secure-icon">♧</span><span>Kept on this device until saved.</span><span className="duration-note">60 SEC</span></div>
              <details className="code-mix-script">
                <summary>Try this code-mix phrase with the microphone</summary>
                <p>{sampleDialect === "hi-IN" ? CODE_MIX_SAMPLES["hi-IN"].transcript : CODE_MIX_SAMPLES["ta-IN"].transcript}</p>
              </details>
            </section>

            <section className="card review-card">
              <div className="card-heading review-heading">
                <div><div className="step-label"><span>02</span> CHECK BEFORE SAVING</div><h2>Review visit details</h2></div>
                {active && <span className={`source-badge ${["evon-v3.3", "gemini", "gemini-argon"].includes(active.extraction_source) ? "source-evon" : ""}`}>{sourceLabel(active.extraction_source)}</span>}
              </div>

              {!active ? (
                <div className="empty-review"><span className="empty-icon">☷</span><strong>No visit selected</strong><p>Record a note or load the sample to start reviewing.</p></div>
              ) : active.state === "processing" ? (
                <div className="processing-state"><span className="spinner" /><div><strong>Preparing your visit note</strong><p>Transcribing your recording…</p></div></div>
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
                  <textarea id="transcript" className="transcript-box" rows={3} value={active.transcript} onChange={(event) => updateTranscript(event.target.value)} disabled={saving} />
                  {active.extraction_source === "demo-parser" && <div className="demo-hint"><span>✦</span> Local extraction</div>}

                  <div className="form-grid">
                    <label className="form-field"><span className="field-label">PATIENT NAME</span><input value={active.visit.patient_name ?? ""} onChange={(event) => updateVisit({ patient_name: event.target.value })} placeholder="Name" disabled={saving} /></label>
                    <label className="form-field"><span className="field-label">AGE</span><div className="input-unit"><input type="number" min="0" max="130" value={active.visit.age ?? ""} onChange={(event) => updateVisit({ age: event.target.value ? Number(event.target.value) : null })} placeholder="—" disabled={saving} /><span>years</span></div></label>
                    <div className="vitals-check span-two"><div className="vitals-check-heading"><strong>Vitals to verify</strong><span>Compare numbers with your notes</span></div><div className="vitals-grid">
                      <label className="form-field"><span className="field-label">BLOOD PRESSURE</span><div className="input-unit"><input value={active.visit.vitals?.blood_pressure ?? ""} onChange={(event) => updateVitals({ blood_pressure: event.target.value })} placeholder="— / —" disabled={saving} /><span>mmHg</span></div></label>
                      <label className="form-field"><span className="field-label">TEMPERATURE</span><div className="input-unit"><input type="number" step="0.1" value={active.visit.vitals?.temperature_f ?? ""} onChange={(event) => updateVitals({ temperature_f: event.target.value ? Number(event.target.value) : null })} placeholder="—" disabled={saving} /><span>°F</span></div></label>
                    </div></div>
                    <label className="form-field span-two"><span className="field-label">SYMPTOMS <small>SEPARATE WITH COMMAS</small></span><input value={symptomsText} onChange={(event) => updateSymptomsText(event.target.value)} placeholder="e.g. mild fever, nausea" disabled={saving} /></label>
                    <label className="form-field"><span className="field-label">FOLLOW-UP DATE</span><input type="date" value={active.visit.follow_up_date ?? ""} onChange={(event) => updateVisit({ follow_up_date: event.target.value || null })} disabled={saving} /></label>
                    <label className="form-field"><span className="field-label">ORIGINAL DATE PHRASE</span><input value={active.visit.follow_up_phrase ?? ""} onChange={(event) => updateVisit({ follow_up_phrase: event.target.value || null })} placeholder="e.g. Friday" disabled={saving} /></label>
                  </div>
                  <div className="review-actions">
                    <button className="button button-quiet" onClick={() => void discardCurrent()} disabled={saving}>Discard draft</button>
                    <button className="button button-primary" onClick={() => void saveCurrentVisit()} disabled={saving}>{saving ? "Saving…" : "Confirm & save visit"}<span>→</span></button>
                  </div>
                </div>
              )}
            </section>
            </div>

            <aside className="right-column">
              {renderFollowUpsCard()}

              <section className="card recent-card">
                <div className="card-heading register-heading"><div><div className="section-kicker">LATEST RECORDS</div><h2>Recent visits</h2></div><button className="inline-link" onClick={() => setCurrentView("register")}>View register →</button></div>
                {activeVisits.length === 0 ? <div className="compact-empty"><span>▤</span><strong>Your register is ready</strong><small>Confirmed visits will show here.</small></div> : <div className="visit-list">{activeVisits.slice(0, 4).map((visit) => <article className="visit-row" key={visit.id}><div className="patient-initials">{initials(visit.visit.patient_name)}</div><div className="visit-row-main"><div className="visit-name-line"><strong>{visit.visit.patient_name || "Unnamed patient"}</strong><span>{formatDate(visit.created_at)}</span></div><p>{visit.visit.age ? `${visit.visit.age} years` : "Age not entered"}{visit.visit.symptoms.length ? ` · ${visit.visit.symptoms.slice(0, 2).join(", ")}` : " · No symptoms listed"}</p></div><button className="row-edit-button" aria-label={`Edit visit for ${visit.visit.patient_name || "unnamed patient"}`} onClick={() => startEditing(visit)}>Edit</button></article>)}</div>}
              </section>

              {queue.length > 0 && (
              <section className="card queue-card">
                <div className="queue-heading"><span>LOCAL DRAFTS</span><div><small>{queue.length} waiting here</small><button className="queue-clear-button" onClick={() => void discardAllDrafts()} disabled={busy || recording}>Clear all</button></div></div>
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
        </>}

        {currentView === "register" && <section className="card register-page-card">
          <div className="register-page-header"><div><span className="section-kicker">CONFIRMED VISITS</span><h2>All active register entries</h2><p>Deleted entries leave this list but remain visible in the audit trail.</p></div><button className="button button-primary" onClick={() => { setCurrentView("dashboard"); window.setTimeout(() => document.getElementById("capture-card")?.scrollIntoView({ behavior: "smooth" }), 80); }}>＋ Capture visit</button></div>
          {loadingPage ? <div className="register-empty">Loading register…</div> : activeVisits.length === 0 ? <div className="register-empty"><span className="register-empty-icon">▤</span><strong>No confirmed visits yet</strong><p>Newly confirmed notes will appear here.</p></div> : <div className="register-table">{activeVisits.map((visit) => <article className="register-table-row" key={visit.id}><div className="patient-initials">{initials(visit.visit.patient_name)}</div><div className="register-person"><strong>{visit.visit.patient_name || "Unnamed patient"}</strong><span>{visit.visit.age ? `${visit.visit.age} years` : "Age not entered"} · {formatDate(visit.created_at)}</span></div><div className="register-symptoms">{visit.visit.symptoms.slice(0, 3).join(", ") || "No symptoms listed"}</div><span className={`sync-status ${visit.sync_state === "pending" ? "status-pending" : ""}`}>{visit.sync_state === "pending" ? "Sync pending" : "Synced"}</span><button className="button button-quiet edit-button" onClick={() => startEditing(visit)}>Edit details</button></article>)}</div>}
          <div className="register-footer"><span className="lock-icon">♧</span><span>Synthetic demo entries only · Audio is not stored with confirmed visits</span></div>
        </section>}

        {currentView === "audit" && <section className="card audit-card">
          <div className="register-page-header"><div><span className="section-kicker">ACCOUNTABILITY</span><h2>Visit activity</h2><p>History stays available when a register entry is edited or deleted.</p></div><span className="count-badge">{auditEvents.length}</span></div>
          {auditEvents.length === 0 ? <div className="register-empty"><span className="register-empty-icon">◷</span><strong>No activity yet</strong><p>Visit creation, edits, follow-up outcomes, and deletions will be listed here.</p></div> : <div className="audit-list">{auditEvents.map((event) => {
            const relatedVisit = visits.find((visit) => visit.id === event.visit_id);
            return <article className="audit-row" key={event.id}><span className={`audit-marker audit-${event.action}`}>{event.action === "created" ? "+" : event.action === "deleted" ? "−" : event.action === "updated" ? "✎" : "✓"}</span><div className="audit-event-copy"><div className="audit-title-line"><strong>{auditActionLabel(event.action)}</strong><span className="audit-time">{new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(event.occurred_at))}</span></div><p>{event.summary}</p><small>{relatedVisit?.visit.patient_name || `Visit ${event.visit_id.slice(0, 8)}`} · {event.actor}{event.sync_state === "pending" ? " · waiting to sync" : ""}</small></div></article>;
          })}</div>}
          <div className="register-footer"><span className="lock-icon">↻</span><span>Audit events are saved locally first and synced when connected.</span></div>
        </section>}

        <footer className={`page-footer ${online ? "" : "footer-offline"}`}>
          <span className="connection-dot" />
          <span>{online ? "Connected" : "Offline · saved locally"}</span>
          <span style={{ margin: '0 4px', opacity: .4 }}>·</span>
          <span>SwarSathi v0.1.0</span>
        </footer>
      </main>
      {editingVisit && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !savingEdit) setEditingVisit(null); }}><section className="edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-title"><div className="modal-heading"><div><span className="section-kicker">REGISTER ENTRY · {formatDate(editingVisit.created_at)}</span><h2 id="edit-title">Edit visit details</h2></div><button className="modal-close" onClick={() => setEditingVisit(null)} aria-label="Close editor" disabled={savingEdit}>×</button></div><div className="review-form edit-form"><label className="field-label" htmlFor="edit-transcript">TRANSCRIPT <span>EDITABLE</span></label><textarea id="edit-transcript" className="transcript-box" rows={3} value={editTranscript} onChange={(event) => setEditTranscript(event.target.value)} disabled={savingEdit} /><div className="form-grid"><label className="form-field"><span className="field-label">PATIENT NAME</span><input value={editFields.patient_name ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, patient_name: event.target.value }))} disabled={savingEdit} /></label><label className="form-field"><span className="field-label">AGE</span><div className="input-unit"><input type="number" min="0" max="130" value={editFields.age ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, age: event.target.value ? Number(event.target.value) : null }))} disabled={savingEdit} /><span>years</span></div></label><label className="form-field"><span className="field-label">BLOOD PRESSURE</span><div className="input-unit"><input value={editFields.vitals?.blood_pressure ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, vitals: { ...current.vitals, blood_pressure: event.target.value } }))} disabled={savingEdit} /><span>mmHg</span></div></label><label className="form-field"><span className="field-label">TEMPERATURE</span><div className="input-unit"><input type="number" step="0.1" value={editFields.vitals?.temperature_f ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, vitals: { ...current.vitals, temperature_f: event.target.value ? Number(event.target.value) : null } }))} disabled={savingEdit} /><span>°F</span></div></label><label className="form-field span-two"><span className="field-label">SYMPTOMS <small>SEPARATE WITH COMMAS</small></span><input value={editSymptomsText} onChange={(event) => setEditSymptomsText(event.target.value)} disabled={savingEdit} /></label><label className="form-field"><span className="field-label">FOLLOW-UP DATE</span><input type="date" value={editFields.follow_up_date ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, follow_up_date: event.target.value || null, follow_up_status: event.target.value ? current.follow_up_status ?? "pending" : undefined }))} disabled={savingEdit} /></label><label className="form-field"><span className="field-label">FOLLOW-UP STATUS</span><select value={editFields.follow_up_status ?? "pending"} onChange={(event) => setEditFields((current) => ({ ...current, follow_up_status: event.target.value as NonNullable<VisitFields["follow_up_status"]> }))} disabled={savingEdit || !editFields.follow_up_date}><option value="pending">Pending</option><option value="completed">Completed</option><option value="missed">Missed</option></select></label><label className="form-field span-two"><span className="field-label">ORIGINAL DATE PHRASE</span><input value={editFields.follow_up_phrase ?? ""} onChange={(event) => setEditFields((current) => ({ ...current, follow_up_phrase: event.target.value || null }))} placeholder="e.g. Friday" disabled={savingEdit} /></label></div><div className="review-note"><span>✓</span><p>Changes are timestamped in the audit trail. Audio is not retained with this register entry.</p></div><div className="modal-actions"><button className="button button-danger" onClick={() => void removeRegisterVisit(editingVisit)} disabled={savingEdit}>Delete visit</button><div><button className="button button-quiet" onClick={() => setEditingVisit(null)} disabled={savingEdit}>Cancel</button><button className="button button-primary" onClick={() => void saveRegisterEdit()} disabled={savingEdit}>{savingEdit ? "Saving…" : "Save changes"}<span>→</span></button></div></div></div></section></div>}
    </div>
  );
}
