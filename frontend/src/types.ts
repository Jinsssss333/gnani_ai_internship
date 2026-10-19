export interface VisitFields {
  patient_name: string | null;
  age: number | null;
  vitals: {
    blood_pressure: string | null;
    temperature_f: number | null;
  };
  symptoms: string[];
  follow_up_date: string | null;
  follow_up_phrase: string | null;
  follow_up_status?: "pending" | "completed" | "missed";
  notes: string | null;
}

export interface VisitRecord {
  id: string;
  created_at: string;
  transcript: string;
  language: string;
  extraction_source: string;
  visit: VisitFields;
  sync_state?: "pending" | "synced";
  deleted_at?: string | null;
}

export interface AuditEvent {
  id: string;
  visit_id: string;
  occurred_at: string;
  action: "created" | "updated" | "deleted" | "follow_up_completed" | "follow_up_missed";
  summary: string;
  actor: string;
  sync_state?: "pending" | "synced";
}

export type QueueState = "waiting" | "processing" | "ready" | "error";

export interface QueuedVisit extends VisitRecord {
  state: QueueState;
  audio?: Blob;
  error?: string;
}

export interface ProviderHealth {
  status: string;
  providers: { prisma: boolean; gemini: boolean; evon: boolean; timbre: boolean };
}
