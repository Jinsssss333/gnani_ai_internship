import type { QueuedVisit, VisitRecord } from "./types";

const DB_NAME = "swarsathi-local";
const QUEUE_STORE = "queued-visits";
const REGISTER_STORE = "saved-visits";
let database: Promise<IDBDatabase> | undefined;

function openDatabase(): Promise<IDBDatabase> {
  if (database) return database;
  database = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(QUEUE_STORE)) db.createObjectStore(QUEUE_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(REGISTER_STORE)) db.createObjectStore(REGISTER_STORE, { keyPath: "id" });
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        database = undefined;
      };
      resolve(db);
    };
    request.onblocked = () => reject(new Error("Reload SwarSathi to finish updating its local storage."));
    request.onerror = () => reject(request.error ?? new Error("Could not open local visit storage."));
  });
  return database;
}

export async function listQueuedVisits(): Promise<QueuedVisit[]> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(QUEUE_STORE, "readonly").objectStore(QUEUE_STORE).getAll();
    request.onsuccess = () => resolve((request.result as QueuedVisit[]).sort((a, b) => b.created_at.localeCompare(a.created_at)));
    request.onerror = () => reject(request.error ?? new Error("Could not load the local visit queue."));
  });
}

export async function getQueuedVisit(id: string): Promise<QueuedVisit | undefined> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(QUEUE_STORE, "readonly").objectStore(QUEUE_STORE).get(id);
    request.onsuccess = () => resolve(request.result as QueuedVisit | undefined);
    request.onerror = () => reject(request.error ?? new Error("Could not load this visit."));
  });
}

export async function putQueuedVisit(visit: QueuedVisit): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(QUEUE_STORE, "readwrite");
    transaction.objectStore(QUEUE_STORE).put(visit);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not save this visit locally."));
  });
}

export async function deleteQueuedVisit(id: string): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(QUEUE_STORE, "readwrite");
    transaction.objectStore(QUEUE_STORE).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not remove this visit locally."));
  });
}

export async function listSavedVisits(): Promise<VisitRecord[]> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(REGISTER_STORE, "readonly").objectStore(REGISTER_STORE).getAll();
    request.onsuccess = () => resolve((request.result as VisitRecord[]).sort((a, b) => b.created_at.localeCompare(a.created_at)));
    request.onerror = () => reject(request.error ?? new Error("Could not load the local register."));
  });
}

export async function putSavedVisit(visit: VisitRecord): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(REGISTER_STORE, "readwrite");
    transaction.objectStore(REGISTER_STORE).put(visit);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not save the visit on this device."));
  });
}
