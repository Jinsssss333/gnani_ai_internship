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
  notes: string | null;
}

export interface VisitRecord {
  id: string;
  created_at: string;
  transcript: string;
  language: string;
  extraction_source: string;
  visit: VisitFields;
}

export type QueueState = "waiting" | "processing" | "ready" | "error";

export interface QueuedVisit extends VisitRecord {
  state: QueueState;
  audio?: Blob;
  error?: string;
}

export interface ProviderHealth {
  status: string;
  providers: { prisma: boolean; evon: boolean; timbre: boolean };
}
