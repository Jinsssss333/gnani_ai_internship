import { useCallback, useEffect, useState } from "react";
import { getAuditEvents, getVisits, getTelephonyStatus, getPhoneCalls } from "./api";
import type { AuditEvent, VisitRecord } from "./types";

type PhoneStatus = Awaited<ReturnType<typeof getTelephonyStatus>>;
type Evidence = { transcript: string; evidence_quote: string; confirmed: boolean; previous_attempts?: { transcript: string }[] };

export default function Supervisor() {
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [phone, setPhone] = useState<PhoneStatus | null>(null);
  const [calls, setCalls] = useState<Awaited<ReturnType<typeof getPhoneCalls>>>([]);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState("");
  const [selected, setSelected] = useState<VisitRecord | null>(null);
  const refresh = useCallback(async () => {
    try {
      const [records, events, status, callLog] = await Promise.all([getVisits(), getAuditEvents(), getTelephonyStatus(), getPhoneCalls()]);
      setCalls(callLog);
      setVisits(records); setAudit(events); setPhone(status); setError("");
      setUpdated(new Date().toLocaleTimeString());
    } catch { setError("Backend unavailable. Previously loaded records remain visible."); }
  }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => clearInterval(timer); }, [refresh]);
  const evidence = (selected?.visit as unknown as { evidence?: Record<string, Evidence> })?.evidence;
  return <div className="supervisor">
    <header><div><strong>SunoCare</strong><span>Listen. Confirm. Care.</span></div><span className="pill">Synthetic demo · Supervisor</span></header>
    <main>
      <section className="intro"><div><p className="eyebrow">PHONE VISIT REGISTER</p><h1>Calls become confirmed records.</h1><p>Workers use their phone keypad and voice. Review the saved results here.</p></div><button onClick={() => void refresh()}>Refresh</button></section>
      {error && <p className="error" role="alert">{error}</p>}
      <section className="phone-status"><div><span className="eyebrow">INBOUND NUMBER</span><h2>{phone?.phone_number || "Awaiting Exotel setup"}</h2><p>{phone?.transport_configured ? "Transport configured · a real call still needs verification" : "Activate an inbound number with the Exotel Voicebot applet to connect the caller."}</p></div><div><strong>{visits.length}</strong><span>Saved visits</span><small>{updated ? `Updated ${updated}` : "Connecting…"}</small></div></section>
      <section className="register"><h2>Visit register</h2>{visits.length === 0 ? <p className="empty">Confirmed phone visits will appear here automatically.</p> : <div className="table-wrap"><table><thead><tr><th>Patient</th><th>Age</th><th>Symptoms</th><th>Follow-up</th><th>Saved</th><th>Evidence</th></tr></thead><tbody>{visits.map(v => <tr key={v.id}><td>{v.visit.patient_name || "Unnamed visit"}</td><td>{v.visit.age ?? "—"}</td><td>{v.visit.symptoms.join(", ") || "—"}</td><td>{v.visit.follow_up_date || v.visit.follow_up_phrase || "—"}</td><td>{new Date(v.created_at).toLocaleString()}</td><td><button onClick={() => setSelected(v)}>Review</button></td></tr>)}</tbody></table></div>}</section>
      <section className="register"><h2>Audit trail</h2>{audit.length ? <ul>{audit.slice(0, 20).map(event => <li key={event.id}><strong>{event.summary}</strong><span>{new Date(event.occurred_at).toLocaleString()} · {event.actor}</span></li>)}</ul> : <p className="empty">No saved events yet.</p>}</section>
      {selected && <section className="register" aria-label="Visit evidence"><div className="intro"><h2>{selected.visit.patient_name || "Visit"} · Evidence</h2><button onClick={() => setSelected(null)}>Close</button></div>{evidence ? Object.entries(evidence).map(([field, answer]) => <article className="evidence" key={field}><strong>{field.replaceAll("_", " ")}</strong><span className="pill">{answer.confirmed ? "Worker confirmed" : "Skipped / unresolved"}</span><blockquote>{answer.transcript || "No answer"}</blockquote><p>Supporting quote: {answer.evidence_quote || "—"}</p>{!!answer.previous_attempts?.length && <details><summary>Previous answers ({answer.previous_attempts.length})</summary>{answer.previous_attempts.map((attempt, i) => <p key={i}>{attempt.transcript}</p>)}</details>}</article>) : <p>{selected.transcript}</p>}</section>}
      <section className="register"><h2>Call log</h2>{calls.length ? <ul>{calls.map(call => <li key={call.call_sid}><strong>{call.status.replaceAll("_", " ")}</strong><span>{new Date(call.started_at).toLocaleString()} · {call.call_sid}</span><span>{call.session_id ? `Visit session: ${call.session_id}` : "Ended before a visit was started"}</span></li>)}</ul> : <p className="empty">No phone calls received yet.</p>}</section>
    </main>
  </div>;
}
