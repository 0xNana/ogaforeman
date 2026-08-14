'use client';

import { ArrowUp, LoaderCircle, Paperclip } from 'lucide-react';
import { FormEvent, useRef, useState } from 'react';
import { ApiRequestError, api, type ConversationMessageResult } from '@/lib/api';
import { SiteComposer } from '@/components/site-composer';

type Turn = { id: string; role: 'user' | 'og'; text: string; result?: ConversationMessageResult };

export function OgConversation({ projectId }: Readonly<{ projectId: string }>) {
  const [message, setMessage] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setTurns((items) => [...items, { id: crypto.randomUUID(), role: 'user', text }]);
    setMessage('');
    key.current ??= `conversation:${crypto.randomUUID()}`;
    try {
      const result = await api.sendConversationMessage(projectId, text, key.current);
      setTurns((items) => [...items, { id: crypto.randomUUID(), role: 'og', text: result.text, result }]);
      key.current = null;
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : 'OG could not reach the project. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return <div className="og-conversation">
    <div className="og-transcript" aria-live="polite" aria-label="Conversation with OG">
      {turns.length === 0 ? <div className="og-empty"><strong>Ask about the project or tell OG what changed.</strong><span>Advice stays read-only. Project changes are shown clearly before they happen.</span></div> : null}
      {turns.map((turn) => <article className={`og-turn ${turn.role}`} key={turn.id}>
        <span className="og-turn-label">{turn.role === 'og' ? responseLabel(turn.result) : 'YOU'}</span>
        {turn.result?.kind === 'proposed_change' && turn.result.proposed_action ? <strong>{turn.result.proposed_action}</strong> : null}
        <p>{turn.text}</p>
      </article>)}
      {busy ? <div className="og-working" role="status"><LoaderCircle size={16} aria-hidden="true" /> OG is checking the current project…</div> : null}
    </div>
    {error ? <p className="auth-error" role="alert">{error}</p> : null}
    <form className="og-message-form" onSubmit={(event) => void submit(event)}>
      <label className="sr-only" htmlFor="og-message">Message OG</label>
      <textarea id="og-message" value={message} onChange={(event) => { setMessage(event.target.value); key.current = null; }} placeholder="Ask OG about this project…" rows={3} />
      <button className="composer-submit" type="submit" aria-label="Send message" disabled={!message.trim() || busy}><ArrowUp size={18} aria-hidden="true" /></button>
    </form>
    <section className="og-site-update" aria-labelledby="og-site-update-title">
      <h3 id="og-site-update-title"><Paperclip size={15} aria-hidden="true" /> Send a site update</h3>
      <SiteComposer projectId={projectId} embedded />
    </section>
  </div>;
}

function responseLabel(result?: ConversationMessageResult): string {
  if (!result) return 'OG';
  if (result.kind === 'proposed_change') return 'PROPOSED CHANGE';
  if (result.kind === 'workflow') return 'WORKFLOW STARTED';
  return result.kind.toUpperCase();
}

export default OgConversation;
