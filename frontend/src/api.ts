import type { AuditEvent, ProviderHealth, QueuedVisit, VisitRecord } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.detail || body.message || `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

export async function getHealth(): Promise<ProviderHealth> {
  const response = await fetch(`${API_BASE}/api/health`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<ProviderHealth>;
}

export async function getVisits(): Promise<VisitRecord[]> {
  const response = await fetch(`${API_BASE}/api/visits`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<VisitRecord[]>;
}

export async function processAudio(audio: Blob, language: string, id: string, signal?: AbortSignal): Promise<QueuedVisit> {
  const form = new FormData();
  form.append("audio_file", audio, `visit-${id}.wav`);
  form.append("language", language);
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener("abort", onAbort, { once: true });
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 45_000);
  try {
    const response = await fetch(`${API_BASE}/api/visits/process`, { method: "POST", body: form, signal: controller.signal });
    if (!response.ok) throw new Error(await readError(response));
    const result = (await response.json()) as Omit<QueuedVisit, "state" | "audio">;
    return { ...result, state: "ready", audio };
  } catch (error) {
    if (timedOut) throw new Error("Transcription timed out after 45 seconds. Your recording is still saved; retry it or clear the draft.");
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", onAbort);
  }
}

export async function getDemoVisit(): Promise<QueuedVisit> {
  return {
    id: `sample-${crypto.randomUUID()}`,
    created_at: new Date().toISOString(),
    transcript: "Amina, 26 years old, blood pressure 120/80, temperature 98.6, mild fever and nausea, follow-up on Friday.",
    language: "hi-IN",
    extraction_source: "synthetic-demo",
    visit: {
      patient_name: "Amina",
      age: 26,
      vitals: { blood_pressure: "120/80", temperature_f: 98.6 },
      symptoms: ["mild fever", "nausea"],
      follow_up_date: null,
      follow_up_phrase: "Friday",
      notes: null,
    },
    state: "ready",
  };
}

export async function saveVisit(visit: VisitRecord): Promise<VisitRecord> {
  const response = await fetch(`${API_BASE}/api/visits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: visit.id,
      created_at: visit.created_at,
      transcript: visit.transcript,
      language: visit.language,
      extraction_source: visit.extraction_source,
      visit: visit.visit,
      deleted_at: visit.deleted_at ?? null,
    }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<VisitRecord>;
}

export async function deleteVisit(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/visits/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readError(response));
}

export async function syncAuditEvent(event: AuditEvent): Promise<void> {
  const response = await fetch(`${API_BASE}/api/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  if (!response.ok) throw new Error(await readError(response));
}

export async function getAuditEvents(): Promise<AuditEvent[]> {
  const response = await fetch(`${API_BASE}/api/audit`);
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<AuditEvent[]>;
}

export async function requestTts(text: string, language: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.blob();
}
