'use client';

import { LoaderCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ApiRequestError, api, type ConversationMessageResult, type PendingConversationProposal } from '@/lib/api';
import { SiteComposer } from '@/components/site-composer';

type Turn = { id: string; role: 'user' | 'og'; text: string; result?: ConversationMessageResult };

export function OgConversation({ projectId }: Readonly<{ projectId: string }>) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ proposal: PendingConversationProposal; memoryVersion: number; label: string } | null>(null);

  useEffect(() => {
    let active = true;
    void api.getPendingConversationProposal(projectId).then((saved) => {
      if (active && saved.proposal) {
        setPending({ proposal: saved.proposal, memoryVersion: saved.memory_version, label: saved.proposal.requested_action });
      }
    }).catch((cause) => {
      if (active && cause instanceof ApiRequestError && cause.status !== 409) setError(cause.message);
    });
    return () => { active = false; };
  }, [projectId]);

  function handleConversationResult(text: string, result: ConversationMessageResult) {
    setTurns((items) => [
      ...items,
      ...(text ? [{ id: crypto.randomUUID(), role: 'user' as const, text }] : []),
      { id: crypto.randomUUID(), role: 'og', text: result.text, result },
    ]);
    if (
      result.kind === 'proposed_change'
      && result.proposal
      && result.memory_version !== null
      && result.memory_version !== undefined
    ) {
      setPending({
        proposal: result.proposal,
        memoryVersion: result.memory_version,
        label: result.proposed_action ?? result.proposal.requested_action,
      });
    }
  }

  async function resolveProposal(decision: 'confirm' | 'cancel') {
    if (!pending || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = decision === 'confirm'
        ? await api.confirmConversationProposal(projectId, pending.proposal.proposal_id, pending.memoryVersion)
        : await api.cancelConversationProposal(projectId, pending.proposal.proposal_id, pending.memoryVersion);
      setPending(null);
      setTurns((items) => [...items, { id: crypto.randomUUID(), role: 'og', text: result.text, result }]);
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : 'OG could not update the proposal. Reload and try again.');
    } finally {
      setBusy(false);
    }
  }

  return <div className="og-conversation">
    <div className="og-transcript" aria-live="polite" aria-label="Conversation with OG">
      {turns.length === 0 ? <div className="og-empty"><strong>Ask about the project or tell OG what changed.</strong><span>Advice stays read-only. Project changes are shown clearly before they happen.</span></div> : null}
      {turns.map((turn) => <article className={`og-turn ${turn.role}`} key={turn.id}>
        <span className="og-turn-label">{turn.role === 'og' ? 'OG' : 'YOU'}</span>
        {turn.result?.kind === 'proposed_change' && turn.result.proposed_action ? <strong>{turn.result.proposed_action}</strong> : null}
        <p>{turn.text}</p>
      </article>)}
      {busy ? <div className="og-working" role="status"><LoaderCircle size={16} aria-hidden="true" /> OG is checking the current project…</div> : null}
    </div>
    {pending ? <section className="og-proposal-card" aria-labelledby={`proposal-${pending.proposal.proposal_id}`}>
      <span>PROPOSED CHANGE</span>
      <h3 id={`proposal-${pending.proposal.proposal_id}`}>{pending.label}</h3>
      <p>OG has not changed the project yet. This proposal expires if the project state changes.</p>
      <div className="og-proposal-actions">
        <button className="btn" type="button" disabled={busy} onClick={() => void resolveProposal('cancel')}>Cancel</button>
        <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void resolveProposal('confirm')}>Confirm</button>
      </div>
    </section> : null}
    {error ? <p className="auth-error" role="alert">{error}</p> : null}
    <SiteComposer
      projectId={projectId}
      embedded
      onConversationResult={handleConversationResult}
    />
  </div>;
}

export default OgConversation;
