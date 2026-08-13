'use client';

import {
  AlertTriangle,
  ArrowUp,
  CheckCircle2,
  FileAudio,
  LoaderCircle,
  Mic,
  Paperclip,
  Plus,
  Square,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ApiRequestError, api, type AgentRunState, type SiteUpdateInput } from '@/lib/api';
import { useProject } from '@/components/project-context';
import { WorkflowReceipt } from '@/components/workflow-receipt';

type IntakeState = 'idle' | 'recording' | 'recorded' | 'uploading' | 'processing' | 'updating' | 'approval' | 'clarification' | 'success' | 'error';

export function SiteComposer({ projectId, embedded = false }: Readonly<{ projectId: string; embedded?: boolean }>) {
  const { refresh } = useProject();
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<IntakeState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<AgentRunState | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const speechRecognition = useRef<any>(null);
  const baseTextRef = useRef('');
  const idempotencyKey = useRef<string | null>(null);
  const uploadedAttachmentId = useRef<string | null>(null);
  const [originalSaved, setOriginalSaved] = useState(false);

  useEffect(() => () => {
    mediaStream.current?.getTracks().forEach((track) => track.stop());
    speechRecognition.current?.stop();
  }, []);

  async function toggleRecording() {
    setError(null);
    if (mediaRecorder.current?.state === 'recording') {
      speechRecognition.current?.stop();
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

      baseTextRef.current = text.trim() ? text.trim() + ' ' : '';
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.onresult = (event: any) => {
          let transcript = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            transcript += event.results[i][0].transcript;
          }
          setText(baseTextRef.current + transcript);
        };
        recognition.start();
        speechRecognition.current = recognition;
      }

      recorder.addEventListener('dataavailable', (event) => {
        if (event.data.size > 0) audioChunks.current.push(event.data);
      });
      recorder.addEventListener('stop', () => {
        const mimeType = recorder.mimeType.split(';')[0] || 'audio/webm';
        const recording = new File(audioChunks.current, 'site-voice-note.webm', { type: mimeType });
        stream.getTracks().forEach((track) => track.stop());
        speechRecognition.current?.stop();
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
      setError('Tell OG what happened, record a note or add a site photo.');
      setState('error');
      return;
    }
    setError(null);
    setOriginalSaved(false);
    try {
      let attachmentId = uploadedAttachmentId.current ?? undefined;
      if (file && !attachmentId) {
        setState('uploading');
        const upload = await api.uploadSiteMedia(projectId, file);
        if (!upload.success) {
          setError(upload.error ?? 'That attachment could not be uploaded.');
          setState('error');
          return;
        }
        attachmentId = upload.attachmentId;
        uploadedAttachmentId.current = attachmentId ?? null;
      }
      setState('processing');
      const input: SiteUpdateInput = {
        rawText: text.trim() || undefined,
        attachmentIds: attachmentId ? [attachmentId] : [],
        inputType: inputTypeFor(text, file),
      };
      idempotencyKey.current ??= `site-update:${crypto.randomUUID()}`;
      const result = await api.submitSiteUpdate(projectId, input, idempotencyKey.current);
      if (result.status !== 'queued') {
        setError('OG could not queue that update.');
        setState('error');
        return;
      }
      const run = await waitForRun(projectId, result.agent_run_id, (currentRun) => {
        if (currentRun.status === 'running') {
          setState('updating');
        }
      });
      setRunResult(run);
      await refresh();
      if (run.status === 'completed') {
        setState('success');
      } else if (run.status === 'waiting_for_approval') {
        setState('approval');
      } else if (run.status === 'waiting_for_clarification') {
        setState('clarification');
      } else {
        setOriginalSaved(true);
        setError(run.error_summary ?? 'OG could not process that update. Try again safely.');
        setState('error');
      }
    } catch (cause) {
      setOriginalSaved(cause instanceof ApiRequestError && cause.code === 'SITE_UPDATE_SAVED_NOT_QUEUED');
      setError(
        cause instanceof ApiRequestError
          ? cause.message
          : 'OG could not reach the project. Check your connection and try again.',
      );
      setState('error');
    }
  }

  function reset() {
    setText('');
    setFile(null);
    setError(null);
    setRunResult(null);
    setOriginalSaved(false);
    idempotencyKey.current = null;
    uploadedAttachmentId.current = null;
    setState('idle');
    speechRecognition.current?.stop();
    speechRecognition.current = null;
    mediaRecorder.current?.stop();
    mediaStream.current?.getTracks().forEach((track) => track.stop());
    mediaRecorder.current = null;
    mediaStream.current = null;
    audioChunks.current = [];
    if (fileInput.current) fileInput.current.value = '';
  }

  const busy = state === 'uploading' || state === 'processing' || state === 'updating';
  const terminal = state === 'success' || state === 'approval';
  const canSubmit = Boolean(text.trim() || file) && state !== 'recording';

  return (
    <div className={`site-composer-page${embedded ? ' embedded' : ''}`}>
      {!embedded && <div className="page-heading"><div><span className="eyebrow">Site update</span><h1>Tell OG what happened.</h1><p>Talk, type or add photos. OG will handle the follow-through.</p></div></div>}
      <section className="site-composer-card" aria-label="Send a site update">
        <input
          ref={fileInput}
          className="attachment-input"
          type="file"
          id="site-attachment"
          accept="image/*,audio/*,.pdf"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            uploadedAttachmentId.current = null;
            idempotencyKey.current = null;
            setError(null);
            if (state === 'recorded') setState('idle');
          }}
        />

        {!terminal && (
          <div className={`chat-composer${state === 'recording' ? ' recording' : ''}`}>
            {state === 'recording' && (
              <div className="composer-media-status recording" role="status">
                <span className="recording-dot" aria-hidden="true" />
                <span>Listening to your update...</span>
                <span className="waveform compact-waveform" aria-hidden="true">{Array.from({ length: 9 }, (_, index) => <span key={index} />)}</span>
              </div>
            )}
            {state === 'recorded' && (
              <div className="recorded-actions" role="status">
                <FileAudio size={15} aria-hidden="true" />
                <span>Voice note ready</span>
              </div>
            )}
            {file && state !== 'recorded' && (
              <div className="attachment-preview" aria-live="polite">
                <Paperclip size={15} aria-hidden="true" />
                <span>{file.name}</span>
              </div>
            )}

            <label className="sr-only" htmlFor="site-update-text">Type a site update</label>
            <textarea
              id="site-update-text"
              className="composer-textarea"
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                idempotencyKey.current = null;
              }}
              placeholder="Tell OG what happened on site..."
              rows={2}
              disabled={busy}
            />

            <div className="chat-composer-actions">
              <button
                className="composer-icon-button"
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={busy || state === 'recording'}
                aria-label="Add attachment"
              >
                <Plus size={21} aria-hidden="true" />
              </button>
              <div className="chat-composer-primary-actions">
                <button
                  className={`composer-icon-button microphone${state === 'recording' ? ' recording' : ''}`}
                  type="button"
                  onClick={toggleRecording}
                  disabled={busy}
                  aria-label={state === 'recording' ? 'Stop recording' : 'Start voice recording'}
                  aria-pressed={state === 'recording'}
                >
                  {state === 'recording' ? <Square size={17} fill="currentColor" aria-hidden="true" /> : <Mic size={20} aria-hidden="true" />}
                </button>
                <button
                  className="composer-icon-button send"
                  type="button"
                  onClick={submit}
                  disabled={busy || !canSubmit}
                  aria-label="Send to OG"
                >
                  {busy ? <LoaderCircle size={19} className="spin-icon" aria-hidden="true" /> : <ArrowUp size={19} aria-hidden="true" />}
                </button>
              </div>
            </div>
          </div>
        )}

        {state === 'error' && (
          <div className="processing-failure" role="alert">
            <span className="empty-state-icon"><AlertTriangle size={18} aria-hidden="true" /></span>
            <div>
              <h2>{originalSaved ? "OG couldn't finish this update." : "OG couldn't send this update."}</h2>
              <p>{originalSaved ? 'Your original site update is saved. Try again when you are ready.' : error}</p>
              {originalSaved && error ? <p className="processing-failure-detail">{error}</p> : null}
              {originalSaved || canSubmit ? <button className="btn btn-primary btn-small" type="button" onClick={() => void submit()}>Try again</button> : null}
            </div>
          </div>
        )}
        {state === 'clarification' && <div className="status-banner info" role="status"><AlertTriangle size={16} /> OG needs a clearer detail before changing the project. Add the task, quantity or timing and send again.</div>}
        {state === 'approval' && <WorkflowReceipt outcome="waiting_for_approval" projectId={projectId} summary={runResult?.result_summary} pendingActions={runResult?.pending_actions} />}
        {state === 'success' && <WorkflowReceipt outcome="completed" projectId={projectId} summary={runResult?.result_summary} pendingActions={runResult?.pending_actions} />}
        {(state === 'uploading' || state === 'processing' || state === 'updating') && (
          <div className="process-state" role="status">
            <div className={`process-state-row${state === 'uploading' ? ' current' : ''}`}>
              {state === 'uploading' ? <span className="process-spinner" /> : <CheckCircle2 size={17} />} Adding your site photos...
            </div>
            <div className={`process-state-row${state === 'processing' ? ' current' : ''}`}>
              {state === 'processing' ? <span className="process-spinner" /> : <CheckCircle2 size={17} />} Checking the project...
            </div>
            <div className={`process-state-row${state === 'updating' ? ' current' : ''}`}>
              {state === 'updating' ? <CheckCircle2 size={17} /> : <LoaderCircle size={17} />} Found project changes...
            </div>
            <div className={`process-state-row${state === 'updating' ? ' current' : ''}`}>
              {state === 'updating' ? <span className="process-spinner" /> : <LoaderCircle size={17} />} Updating the site...
            </div>
          </div>
        )}

        {terminal && <div className="composer-reset"><button className="btn btn-quiet" type="button" onClick={reset}>Send another update</button></div>}
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

async function waitForRun(projectId: string, runId: string, onUpdate?: (run: AgentRunState) => void): Promise<AgentRunState> {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const run = await api.getAgentRun(projectId, runId);
    if (onUpdate) onUpdate(run);
    if (['completed', 'failed', 'dead_lettered', 'waiting_for_approval', 'waiting_for_clarification'].includes(run.status)) {
      return run;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  throw new Error('site update processing timed out');
}
