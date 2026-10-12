import type { QueuedVisit } from "./types";

const DB_NAME = "swarsathi-local";
const STORE_NAME = "queued-visits";
let database: Promise<IDBDatabase> | undefined;

function openDatabase(): Promise<IDBDatabase> {
  if (database) return database;
  database = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open local visit storage."));
  });
  return database;
}

export async function listQueuedVisits(): Promise<QueuedVisit[]> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).getAll();
    request.onsuccess = () => resolve((request.result as QueuedVisit[]).sort((a, b) => b.created_at.localeCompare(a.created_at)));
    request.onerror = () => reject(request.error ?? new Error("Could not load the local visit queue."));
  });
}

export async function getQueuedVisit(id: string): Promise<QueuedVisit | undefined> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(id);
    request.onsuccess = () => resolve(request.result as QueuedVisit | undefined);
    request.onerror = () => reject(request.error ?? new Error("Could not load this visit."));
  });
}

export async function putQueuedVisit(visit: QueuedVisit): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(visit);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not save this visit locally."));
  });
}

export async function deleteQueuedVisit(id: string): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not remove this visit locally."));
  });
}
