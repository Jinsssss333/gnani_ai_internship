import { useState } from "react";
import { actOnCall, answerCall, finalizeCall, startCall, type CallSession } from "./api";

type Props = { onClose: () => void; onSaved: () => void };

const languages = [
  { code: "hi-IN", label: "Hindi / Hinglish" },
  { code: "ml-IN", label: "Malayalam" },
  { code: "ta-IN", label: "Tamil" },
  { code: "en-IN", label: "English" },
];

function displayValue(value: unknown): string {
  if (typeof value === "object" && value !== null) return Object.values(value as Record<string, string>).filter(Boolean).join(" · ");
  return String(value ?? "Not recorded");
}

export default function CallSessionScreen({ onClose, onSaved }: Props) {
  const [language, setLanguage] = useState("hi-IN");
  const [visitCode, setVisitCode] = useState("4821");
  const [session, setSession] = useState<CallSession | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function run(task: () => Promise<void>) {
    setBusy(true); setError("");
    try { await task(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Please try again."); } finally { setBusy(false); }
  }

  const currentAnswer = session?.prompt ? session.answers[session.prompt.id] : undefined;

  if (saved) return <main className="call-page"><section className="call-card saved-call"><span>✓</span><p className="section-kicker">VISIT CONFIRMED</p><h1>Saved in SunoCare</h1><p>The guided visit is in the register and audit trail.</p><button className="button button-primary" onClick={onSaved}>Open dashboard</button></section></main>;

  if (!session) return <main className="call-page"><section className="call-card">
    <button className="call-back" onClick={onClose}>← Dashboard</button><p className="section-kicker">GUIDED VISIT</p><h1>Start a visit call</h1><p>Use only synthetic household codes in this prototype.</p>
    <label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}>{languages.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
    <label>Visit code<input inputMode="numeric" value={visitCode} onChange={(event) => setVisitCode(event.target.value)} maxLength={4} /></label>
    {error && <p className="call-error">{error}</p>}<button className="button button-primary call-primary" disabled={busy} onClick={() => run(async () => setSession(await startCall(language, visitCode)))}>{busy ? "Starting…" : "Start guided visit"}</button>
  </section></main>;

  if (session.state === "FINAL_REVIEW") return <main className="call-page"><section className="call-card">
    <p className="section-kicker">FINAL REVIEW</p><h1>Check the visit</h1><div className="call-summary">{Object.values(session.answers).map((answer) => <div key={answer.answer_id}><span>{answer.question_id.replaceAll("_", " ")}</span><strong>{displayValue(answer.value)}</strong><small>{answer.confirmed ? "Confirmed" : "Unresolved"}</small></div>)}</div>
    {error && <p className="call-error">{error}</p>}<button className="button button-primary call-primary" disabled={busy} onClick={() => run(async () => { await finalizeCall(session.session_id); setSaved(true); })}>{busy ? "Saving…" : "Save confirmed visit"}</button>
  </section></main>;

  const keypad = session.prompt?.expects.keypad;
  return <main className="call-page"><section className="call-card">
    <button className="call-back" onClick={onClose}>× Exit call</button><p className="section-kicker">GUIDED VISIT · {session.visit_code}</p><div className="call-progress">Question {Object.keys(session.answers).length + 1}</div><h1>{session.prompt?.text}</h1>
    {currentAnswer ? <section className="call-result"><span>Heard</span><strong>{displayValue(currentAnswer.value)}</strong><p>Evidence: “{currentAnswer.evidence_quote}”</p><div className="call-actions"><button disabled={busy} onClick={() => run(async () => setSession(await actOnCall(session.session_id, "confirm")))}>✓ Confirm</button><button disabled={busy} onClick={() => run(async () => { await actOnCall(session.session_id, "correct"); setInput(""); setSession({ ...session, answers: { ...session.answers, [currentAnswer.question_id]: { ...currentAnswer, confirmed: false } } }); })}>Correct</button><button disabled={busy} onClick={() => run(async () => setSession(await actOnCall(session.session_id, "repeat")))}>Repeat</button>{session.prompt?.expects.optional && <button disabled={busy} onClick={() => run(async () => setSession(await actOnCall(session.session_id, "skip")))}>Skip</button>}</div></section> : <>
      {keypad ? <div className="call-keypad">{Object.entries(keypad).map(([key, value]) => <button key={key} disabled={busy} onClick={() => run(async () => setSession(await answerCall(session.session_id, crypto.randomUUID(), session.prompt!.id, undefined, key)))}><strong>{key}</strong>{String(value).replaceAll("_", " ")}</button>)}</div> : <><label>Your answer<input autoFocus value={input} onChange={(event) => setInput(event.target.value)} placeholder={session.prompt?.expects.type === "integer" ? "Enter age" : "Type the response for this demo"} /></label><button className="button button-primary call-primary" disabled={busy || !input.trim()} onClick={() => run(async () => setSession(await answerCall(session.session_id, crypto.randomUUID(), session.prompt!.id, input)))}>{busy ? "Checking…" : "Continue"}</button></>}
    </>}{error && <p className="call-error">{error}</p>}
  </section></main>;
}
