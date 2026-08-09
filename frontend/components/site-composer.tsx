'use client';

import {
  AlertTriangle,
  CheckCircle2,
  FileAudio,
  Image as ImageIcon,
  LoaderCircle,
  Mic,
  Paperclip,
  RotateCcw,
  Send,
  Square,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, type AgentRunState, type SiteUpdateInput } from '@/lib/api';
import { WorkflowReceipt } from '@/components/workflow-receipt';

type IntakeState = 'idle' | 'recording' | 'recorded' | 'uploading' | 'processing' | 'approval' | 'clarification' | 'success' | 'error';

export function SiteComposer({ projectId }: Readonly<{ projectId: string }>) {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<IntakeState>('idle');
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  useEffect(() => () => {
    mediaStream.current?.getTracks().forEach((track) => track.stop());
  }, []);

  async function toggleRecording() {
    setError(null);
    if (mediaRecorder.current?.state === 'recording') {
      mediaRecorder.current.requestData();
      mediaRecorder.current.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Voice recording is not supported in this browser. Type the update instead.');
      setState('error');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaStream.current = stream;
      mediaRecorder.current = recorder;
      audioChunks.current = [];
      recorder.addEventListener('dataavailable', (event) => {
        if (event.data.size > 0) audioChunks.current.push(event.data);
      });
      recorder.addEventListener('stop', () => {
        const mimeType = recorder.mimeType.split(';')[0] || 'audio/webm';
        const recording = new File(audioChunks.current, 'site-voice-note.webm', { type: mimeType });
        stream.getTracks().forEach((track) => track.stop());
        mediaStream.current = null;
        mediaRecorder.current = null;
        if (recording.size === 0) {
          setError('No audio was captured. Try recording again or type the update.');
          setState('error');
          return;
        }
        setFile(recording);
        setState('recorded');
      }, { once: true });
      recorder.start();
      setState('recording');
    } catch {
      setError('Microphone access was denied. Allow it in your browser or type the update.');
      setState('error');
    }
  }

  async function submit() {
    if (!text.trim() && !file && state !== 'recorded') {
      setError('Tell Oga what happened, record a note or add a site photo.');
      setState('error');
      return;
    }
    setError(null);
    try {
      let attachmentId: string | undefined;
      if (file) {
        setState('uploading');
        const upload = await api.uploadSiteMedia(projectId, file);
        if (!upload.success) {
          setError(upload.error ?? 'That attachment could not be uploaded.');
          setState('error');
          return;
        }
        attachmentId = upload.attachmentId;
      }
      setState('processing');
      const input: SiteUpdateInput = {
        rawText: text.trim() || undefined,
        attachmentIds: attachmentId ? [attachmentId] : [],
        inputType: inputTypeFor(text, file),
      };
      const result = await api.submitSiteUpdate(projectId, input);
      if (result.status !== 'queued') {
        setError('Oga could not queue that update.');
        setState('error');
        return;
      }
      const run = await waitForRun(projectId, result.agent_run_id);
      if (run.status === 'completed') {
        setState('success');
      } else if (run.status === 'waiting_for_approval') {
        setState('approval');
      } else if (run.status === 'waiting_for_clarification') {
        setState('clarification');
      } else {
        setError(run.error_summary ?? 'Oga could not process that update. Try again safely.');
        setState('error');
      }
    } catch {
      setError('Oga could not reach the project. Check your connection and try again.');
      setState('error');
    }
  }

  function reset() {
    setText('');
    setFile(null);
    setError(null);
    setState('idle');
    mediaRecorder.current?.stop();
    mediaStream.current?.getTracks().forEach((track) => track.stop());
    mediaRecorder.current = null;
    mediaStream.current = null;
    audioChunks.current = [];
    if (fileInput.current) fileInput.current.value = '';
  }

  const busy = state === 'uploading' || state === 'processing';

  return (
    <div className="site-composer-page">
      <div className="page-heading"><div><span className="eyebrow">Site update</span><h1>Tell Oga what happened.</h1><p>Talk, type or add photos. Oga will handle the follow-through.</p></div></div>
      <section className="site-composer-card" aria-labelledby="site-composer-title">
        <span className="composer-kicker">Ridge House · Today</span>
        <h2 id="site-composer-title">What happened today?</h2>
        <p>Short and natural works best. Say what finished, what is stuck and what is running low.</p>

        <div className="site-recording-area">
          <button className={`record-button${state === 'recording' ? ' recording' : ''}`} type="button" onClick={toggleRecording} disabled={busy} aria-label={state === 'recording' ? 'Stop recording' : 'Start voice recording'}>
            {state === 'recording' ? <Square size={24} fill="currentColor" /> : <Mic size={28} />}
          </button>
          <div><strong>{state === 'recording' ? 'Listening...' : state === 'recorded' ? 'Voice note ready' : 'Hold to talk to Oga'}</strong><span>{state === 'recording' ? '00:14 · Tap when you are done' : state === 'recorded' ? 'Use this recording or record again' : 'Voice updates are fastest on site'}</span></div>
          {state === 'recording' && <span className="waveform site-waveform" aria-hidden="true">{Array.from({ length: 15 }, (_, index) => <span key={index} />)}</span>}
        </div>

        {state === 'recorded' && <div className="recorded-actions"><span><FileAudio size={16} /> Voice note ready</span><button type="button" onClick={toggleRecording}><RotateCcw size={14} /> Record again</button></div>}

        <label className="sr-only" htmlFor="site-update-text">Type a site update</label>
        <textarea id="site-update-text" className="composer-textarea" value={text} onChange={(event) => setText(event.target.value)} placeholder="First-floor blockwork is done. The electrician didn't show. We have about 10 bags of cement left..." disabled={busy || state === 'success'} />

        <input ref={fileInput} className="attachment-input" type="file" id="site-attachment" accept="image/*,audio/*,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        {file && <div className="attachment-preview"><Paperclip size={15} /> {file.name}</div>}

        {state === 'error' && <div className="status-banner error" role="alert"><AlertTriangle size={16} /> {error}</div>}
        {state === 'clarification' && <div className="status-banner info" role="status"><AlertTriangle size={16} /> Oga needs a clearer detail before changing the project. Add the task, quantity or timing and send again.</div>}
        {state === 'approval' && <WorkflowReceipt outcome="waiting_for_approval" projectId={projectId} />}
        {state === 'success' && <WorkflowReceipt outcome="completed" projectId={projectId} />}
        {(state === 'uploading' || state === 'processing') && <div className="process-state" role="status"><div className={`process-state-row${state === 'uploading' ? ' current' : ''}`}>{state === 'uploading' ? <span className="process-spinner" /> : <CheckCircle2 size={17} />} Adding your site photos...</div><div className={`process-state-row${state === 'processing' ? ' current' : ''}`}>{state === 'processing' ? <span className="process-spinner" /> : <LoaderCircle size={17} />} Checking the project...</div><div className="process-state-row"><CheckCircle2 size={17} /> Updating the site...</div></div>}

        <div className="composer-bottom">
          <label className="attachment-button" htmlFor="site-attachment"><ImageIcon size={16} /> {file ? 'Change attachment' : 'Add photos or file'}</label>
          {state === 'success' || state === 'approval' ? <button className="btn btn-quiet" type="button" onClick={reset}>Send another update</button> : <button className="btn btn-accent" type="button" onClick={submit} disabled={busy}><Send size={16} /> {busy ? 'Oga is working...' : 'Send to Oga'}</button>}
        </div>
      </section>
    </div>
  );
}

function inputTypeFor(text: string, file: File | null): SiteUpdateInput['inputType'] {
  if (!file) return 'text';
  if (text.trim()) return 'mixed';
  if (file.type.startsWith('audio/')) return 'voice';
  if (file.type.startsWith('image/')) return 'photo';
  return 'file';
}

async function waitForRun(projectId: string, runId: string): Promise<AgentRunState> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const run = await api.getAgentRun(projectId, runId);
    if (['completed', 'failed', 'dead_lettered', 'waiting_for_approval', 'waiting_for_clarification'].includes(run.status)) {
      return run;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  throw new Error('site update processing timed out');
}
