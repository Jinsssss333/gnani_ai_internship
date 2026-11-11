import { useEffect, useRef, useState } from "react";
import { convertToWav } from "./audio";
import { answerCallAudio, requestTts, type CallSession } from "./api";

export default function VoiceAnswer({ session, onAnswer }: { session: CallSession; onAnswer: (s: CallSession) => void }) {
  const recorder = useRef<MediaRecorder | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [clip, setClip] = useState<Blob | null>(null);
  useEffect(() => () => { clearTimeout(timer.current); player.current?.pause(); if (recorder.current) { recorder.current.onstop = null; recorder.current.stream.getTracks().forEach(t => t.stop()); } }, []);
  async function submit(audio: Blob) {
    setBusy(true); setError("");
    try { onAnswer(await answerCallAudio(session.session_id, session.state, audio)); setClip(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Please retry."); }
    finally { setBusy(false); }
  }
  async function record() {
    player.current?.pause(); setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream); recorder.current = r;
      const chunks: Blob[] = [];
      r.ondataavailable = e => chunks.push(e.data);
      r.onstop = async () => {
        clearTimeout(timer.current); stream.getTracks().forEach(t => t.stop()); setRecording(false); setBusy(true);
        try { const wav = await convertToWav(new Blob(chunks, { type: r.mimeType })); setClip(wav); await submit(wav); }
        catch { setError("Could not prepare the recording. Please try again."); }
        finally { setBusy(false); }
      };
      r.start(); setRecording(true);
      timer.current = window.setTimeout(() => { if (r.state === "recording") r.stop(); }, 25000);
    } catch { setError("Microphone unavailable. Allow microphone access or type your answer."); }
  }
  async function speak() {
    setBusy(true); setError("");
    try {
      const answer = session.answers[session.state];
      const text = answer && !answer.awaiting_replacement ? `You said: ${answer.transcript}` : session.prompt?.text || "Review your visit.";
      const blob = await requestTts(text, "en-IN");
      player.current?.pause();
      const url = URL.createObjectURL(blob); const audio = new Audio(url); player.current = audio;
      audio.onended = () => URL.revokeObjectURL(url); await audio.play();
    } catch { setError("Read-back unavailable. You can continue using the displayed text."); }
    finally { setBusy(false); }
  }
  return <section aria-label="Voice answer">
    <button disabled={busy || recording} onClick={() => void speak()}>Hear question / answer</button>
    <button disabled={busy} onClick={() => recording ? recorder.current?.stop() : void record()}>{recording ? "1 · Finish speaking" : "Record answer · max 25 seconds"}</button>
    {busy && <p role="status">Processing…</p>}
    {error && <p role="alert">{error}</p>}
    {clip && !busy && <button onClick={() => void submit(clip)}>Retry saved recording</button>}
  </section>;
}
