'use client';

import { ArrowRight, CheckCircle2, ShieldCheck, XCircle } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { ApiRequestError, api, type Approval, type Task } from '@/lib/api';

type ApprovalListProps = {
  approvals: Approval[];
  followUps: Task[];
  projectId: string;
  onRefresh: () => Promise<void>;
};

export function ApprovalList({ approvals: initialApprovals, followUps, projectId, onRefresh }: Readonly<ApprovalListProps>) {
  const [resolvedApprovals, setResolvedApprovals] = useState<Record<string, Approval>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const approvals = initialApprovals.map((approval) => resolvedApprovals[approval.id] ?? approval);
  const pendingCount = approvals.filter((approval) => approval.status === 'PENDING').length;
  const waitingCount = pendingCount + followUps.length;

  async function decide(approvalId: string, decision: 'APPROVE' | 'REJECT') {
    const approval = approvals.find((item) => item.id === approvalId);
    if (!approval || approval.status !== 'PENDING') return;
    setBusy(approvalId);
    setError(null);
    try {
      const updated = await api.resolveApproval(projectId, approvalId, decision, approval.version);
      setResolvedApprovals((items) => ({ ...items, [approvalId]: updated }));
      try {
        await onRefresh();
      } catch {
        setError('The decision was saved, but the project view could not refresh. Refresh to see the latest state.');
      }
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.code === 'CONFLICT_VERSION_MISMATCH') {
        setError('This approval changed after you opened it. Refresh before deciding.');
      } else {
        setError('That decision could not be saved. Reload the project and try again.');
      }
    } finally {
      setBusy(null);
    }
  }

  async function refreshApprovals() {
    await onRefresh();
    setError(null);
  }

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Human control</span><h1>Needs you</h1><p>Important actions stay yours. {waitingCount > 0 ? `${waitingCount} item${waitingCount === 1 ? '' : 's'} waiting.` : 'Nothing is waiting.'}</p></div></div>
      {error && <div className="status-banner error" role="alert"><span>{error}</span><button className="auth-text-button" type="button" onClick={() => void refreshApprovals()}>Refresh approvals</button></div>}
      {approvals.length > 0 || followUps.length > 0 ? <div className="approval-list">{followUps.map((task) => <FollowUpCard key={task.id} task={task} projectId={projectId} />)}{approvals.map((approval) => <article className="approval-resource-card" key={approval.id}><div className="approval-resource-head"><span className={`status-pill ${approval.status.toLowerCase()}`}>{approval.status}</span><span>{approval.date}</span></div><span className="needs-type">{approval.type}</span><h2>{approval.title}</h2><dl className="approval-resource-details"><div><dt>Oga recommends</dt><dd>{approval.quantity}</dd></div><div><dt>Needed by</dt><dd>{approval.neededBy}</dd></div><div><dt>Requested by</dt><dd>{approval.requestedBy}</dd></div></dl><p>{approval.reason}</p>{approval.status === 'PENDING' ? <div className="approval-actions"><button className="btn btn-primary" type="button" disabled={busy === approval.id} onClick={() => decide(approval.id, 'APPROVE')}>{busy === approval.id ? 'Saving...' : 'Approve'}</button><button className="btn btn-quiet" type="button" disabled={busy === approval.id} onClick={() => decide(approval.id, 'REJECT')}>Reject</button></div> : <DecisionReceipt approval={approval} projectId={projectId} />}</article>)}</div> : <div className="empty-state"><span className="empty-state-icon"><ShieldCheck size={20} /></span><h2>You&apos;re clear.</h2><p>Nothing needs your approval right now.</p></div>}
    </div>
  );
}

function FollowUpCard({ task, projectId }: Readonly<{ task: Task; projectId: string }>) {
  return (
    <article className="approval-resource-card">
      <div className="approval-resource-head"><span className="status-pill pending">PENDING</span><span>{task.dueLabel}</span></div>
      <span className="needs-type">Follow-up</span>
      <h2>{task.title}</h2>
      <dl className="approval-resource-details"><div><dt>Assigned to</dt><dd>{task.assignee}</dd></div><div><dt>Source</dt><dd>Site update</dd></div></dl>
      {task.note ? <p>{task.note}</p> : null}
      <div className="approval-actions"><Link className="btn btn-quiet" href={`/projects/${projectId}/tasks`}>Open in Tasks <ArrowRight size={13} /></Link></div>
    </article>
  );
}

function DecisionReceipt({ approval, projectId }: Readonly<{ approval: Approval; projectId: string }>) {
  const approved = approval.status === 'APPROVED';
  return (
    <div className={`decision-receipt ${approved ? 'approved' : 'rejected'}`} role="status">
      <span className="decision-receipt-icon" aria-hidden="true">
        {approved ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
      </span>
      <div>
        <strong>{approved ? 'Approval recorded' : 'Request closed'}</strong>
        <p>
          {approved
            ? 'Oga is resuming from the saved checkpoint.'
            : 'No supplier or external action will run.'}
        </p>
        <Link href={`/projects/${projectId}/activity`}>
          Follow in activity <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}
