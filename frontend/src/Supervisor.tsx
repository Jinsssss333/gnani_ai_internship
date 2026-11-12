import { useCallback, useEffect, useRef, useState } from "react";
import { getAuditEvents, getVisits, getPhoneCalls, getPendingSessions, repairSession, finalizeCall } from "./api";
import type { PendingSession } from "./api";
import RegisterExport from './RegisterExport';
import type { AuditEvent, VisitRecord } from "./types";

const label = (text: string) => text.replaceAll("_", " ");
function display(value: unknown): string {
  if (value == null) return "Not provided";
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') {
    const v = value as Record<string, unknown>;
    if (v.date) return String(v.date).split('-').reverse().join('/');
    return Object.entries(v)
      .filter(([k, x]) => k !== 'negated' || (Array.isArray(x) && x.some(item => String(item).trim())))
      .map(([k,x]) => `${k === 'negated' ? 'Symptoms denied' : k === 'reported' ? 'Reported' : label(k)}: ${Array.isArray(x) ? x.join(', ') || 'None' : x}`).join(' · ');
  }
  return String(value);
}
export default function Supervisor() {
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [pending, setPending] = useState<PendingSession[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [calls, setCalls] = useState<Awaited<ReturnType<typeof getPhoneCalls>>>([]);
  const [tab, setTab] = useState('register');
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState('');
  const loading = useRef(false);
  const refresh = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    try {
      // Register updates do not depend on the phone-status or audit services.
      const [v, p] = await Promise.all([getVisits(), getPendingSessions()]);
      setVisits(v); setPending(p); setError(''); setUpdated(new Date().toLocaleTimeString());
      const results = await Promise.allSettled([getAuditEvents(), getPhoneCalls()]);
      if (results[0].status === 'fulfilled') setAudit(results[0].value);
      if (results[1].status === 'fulfilled') setCalls(results[1].value);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to refresh.'); }
    finally { loading.current = false; }
  }, []);
  useEffect(() => { void refresh(); const id = window.setInterval(() => void refresh(), 3000); return () => clearInterval(id); }, [refresh]);
  const draft = pending.find(p => p.id === selected);
  const saved = visits.find(v => v.id === selected);
  const answers = draft?.answers || (saved?.visit as unknown as {evidence?: PendingSession['answers']})?.evidence;
  const field = draft?.missing_field;
  useEffect(() => setInput(''), [selected, field]);
  async function resolve(submit = false) {
    if (!draft) return;
    setBusy(true);
    try {
      if (submit) await finalizeCall(draft.id);
      else await repairSession(draft.id, draft.missing_field, input);
      await refresh();
    } catch(e) { setError(e instanceof Error ? e.message : 'Could not save.'); }
    finally { setBusy(false); }
  }
  const rows = [
    ...pending.map(p => ({id:p.id, name:display(p.answers.patient_name?.value), code:p.visit_code, status:p.record_status, date:p.updated_at, detail:p.missing_field === 'FINAL_REVIEW' ? 'Ready to submit' : `Next: ${label(p.missing_field)}`})),
    ...visits.map(v => ({id:v.id, name:v.visit.patient_name || 'Home visit', code:String((v.visit as unknown as {visit_code?: string}).visit_code || '—'), status:'submitted', date:v.created_at, detail:v.visit.follow_up_date ? `Follow-up ${display({date:v.visit.follow_up_date})}` : v.visit.follow_up_phrase ? `Follow-up: ${v.visit.follow_up_phrase}` : 'No follow-up date'}))
  ].filter(r => filter === 'all' || r.status === filter);
  return <div className="supervisor">
    <header><strong>SunoCare<span className="brand-dot">●</span></strong></header>
    <div className="layout"><nav aria-label="Workspace">{[['register','Visit register'],['calls','Calls'],['audit','Audit trail']].map(([id,text]) => <button key={id} aria-current={tab===id?'page':undefined} onClick={()=>setTab(id)}>{text}</button>)}</nav>
    <main><div className="intro"><div><p className="eyebrow">SUPERVISOR</p><h1>{tab==='register'?'Visit register':tab==='calls'?'Calls':'Audit trail'}</h1><small>{updated ? `Updated ${updated} · Refreshes every 3s` : 'Connecting…'}</small></div><button onClick={()=>void refresh()}>Refresh</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    {tab==='register' && <><div className="metrics">{[['Submitted',visits.length],['Needs review',pending.filter(p=>p.record_status==='needs_review').length],['In progress',pending.filter(p=>p.record_status==='in_progress').length]].map(([title,count])=><div key={title}><span>{title}</span><strong>{count}</strong></div>)}</div>
    <RegisterExport visits={visits}/>
    <div className="filters" aria-label="Record status">{['all','in_progress','needs_review','submitted'].map(f=><button key={f} aria-pressed={filter===f} onClick={()=>setFilter(f)}>{label(f)}</button>)}</div>
    <section className="register"><div className="table-wrap"><table><thead><tr><th>Patient / code</th><th>Status</th><th>Details</th><th>Updated</th><th></th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><strong>{r.name}</strong><small>{r.code}</small></td><td><span className={`pill ${r.status}`}>{label(r.status)}</span></td><td>{r.detail}</td><td>{new Date(r.date).toLocaleString('en-IN')}</td><td><button onClick={()=>setSelected(r.id)}>Open</button></td></tr>)}</tbody></table></div>{!rows.length && <p className="empty">No records here yet.</p>}</section>
    {selected && (draft || saved) && <section className="register" aria-label="Record details"><div className="intro"><h2>{draft ? 'Review draft' : 'Submitted visit'}</h2><button onClick={()=>setSelected(null)}>Close</button></div><div className="field-grid">{!answers && saved && Object.entries(saved.visit).filter(([key]) => ["patient_name","age","symptoms","follow_up_date","follow_up_phrase","notes"].includes(key)).map(([key,value]) => <article key={key}><small>{label(key)}</small><p>{Array.isArray(value) ? value.join(", ") : key === "follow_up_date" && value ? display({date:value}) : display(value)}</p></article>)}{Object.entries(answers || {}).map(([key,a])=><article key={key}><small>{label(key)}</small><p>{display(a.value)}</p><span className="pill">{a.confirmed ? 'Confirmed' : a.unresolved && ['notes','symptoms'].includes(key) ? 'Optional · skipped' : 'Needs review'}</span></article>)}</div>
    {draft?.record_status==='in_progress' && <p>Call in progress. Answers update automatically.</p>}
    {draft?.record_status==='needs_review' && (field==='FINAL_REVIEW' ? <button disabled={busy} onClick={()=>void resolve(true)}>Confirm and submit visit</button> : <form onSubmit={e=>{e.preventDefault();void resolve();}}><label htmlFor="repair">Resolve {label(field || '')}</label>
    {['visit_done','followup_needed','not_done_reason'].includes(field || '') ? <select id="repair" required value={input} onChange={e=>setInput(e.target.value)}><option value="">Select…</option>{(field==='not_done_reason' ? [['1','House locked'],['2','Patient away'],['3','Refused'],['4','Other']] : [['1','Yes'],['2','No']]).map(([v,t])=><option key={v} value={v}>{t}</option>)}</select> : <input id="repair" required={!["notes", "symptoms"].includes(field || "")} type={field==='followup_date'?'date':field==='age'?'number':'text'} min={field==='age'?0:undefined} max={field==='age'?120:undefined} value={input} onChange={e=>setInput(e.target.value)}/>}
    <button disabled={busy}>Confirm answer</button></form>)}</section>}</>}
    {tab==='calls' && <section className="register"><ul>{calls.map(c=><li key={c.call_sid}><strong>{label(c.status)}</strong><span>{new Date(c.started_at).toLocaleString()}</span>{c.session_id && <button onClick={()=>{setSelected(c.session_id);setTab('register');}}>Open record</button>}</li>)}</ul>{!calls.length && <p>No calls yet.</p>}</section>}
    {tab==='audit' && <section className="register"><ul>{audit.map(e=><li key={e.id}><strong>{e.summary}</strong><span>{new Date(e.occurred_at).toLocaleString()} · {e.actor}</span></li>)}</ul>{!audit.length && <p>No changes yet.</p>}</section>}
    </main></div></div>;
}
