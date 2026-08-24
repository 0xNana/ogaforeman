'use client';

import { ArrowRight, CheckCircle2, ShieldCheck, XCircle } from 'lucide-react';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { ApiRequestError, api, type Approval, type Task } from '@/lib/api';
import { Pagination } from '@/components/pagination';

type ApprovalListProps = {
  approvals: Approval[];
  followUps: Task[];
  projectId: string;
  onRefresh: () => Promise<void>;
};

export function ApprovalList({ approvals: initialApprovals, followUps, projectId, onRefresh }: Readonly<ApprovalListProps>) {
  const [resolvedApprovals, setResolvedApprovals] = useState<Record<string, Approval>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const approvals = [
    ...initialApprovals.map((approval) => resolvedApprovals[approval.id] ?? approval),
    ...Object.values(resolvedApprovals).filter(
      (approval) => !initialApprovals.some((item) => item.id === approval.id),
    ),
  ];
  const pendingCount = approvals.filter((approval) => approval.status === 'PENDING').length;
  const waitingCount = pendingCount + followUps.length;

  const items = useMemo(() => {
    return [
      ...followUps.map(t => ({ type: 'task' as const, data: t })),
      ...approvals.map(a => ({ type: 'approval' as const, data: a }))
    ];
  }, [followUps, approvals]);

  const [page, setPage] = useState(1);
  const pageSize = 15;
  const paginatedItems = useMemo(() => {
    return items.slice((page - 1) * pageSize, page * pageSize);
  }, [items, page, pageSize]);

  async function decide(approvalId: string, decision: 'APPROVE' | 'REJECT') {
    const approval = approvals.find((item) => item.id === approvalId);
    if (!approval || approval.status !== 'PENDING') return;
    setBusy(approvalId);
    setErrors((items) => ({ ...items, [approvalId]: '' }));
    try {
      const updated = await api.resolveApproval(projectId, approvalId, decision, approval.version);
      setResolvedApprovals((items) => ({ ...items, [approvalId]: updated }));
      try {
        await onRefresh();
      } catch {
        setErrors((items) => ({ ...items, [approvalId]: 'The decision was saved, but the project view could not refresh. Refresh to see the latest state.' }));
      }
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.code === 'CONFLICT_VERSION_MISMATCH') {
        setErrors((items) => ({ ...items, [approvalId]: 'This request has already been resolved. Refresh to see the latest status.' }));
      } else {
        setErrors((items) => ({ ...items, [approvalId]: 'That decision could not be saved. Refresh the project and try again.' }));
      }
    } finally {
      setBusy(null);
    }
  }

  async function refreshApprovals() {
    await onRefresh();
    setErrors({});
  }

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Human control</span><h1>Needs you</h1><p>Important actions stay yours. {waitingCount > 0 ? `${waitingCount} item${waitingCount === 1 ? '' : 's'} waiting.` : 'Nothing is waiting.'}</p></div></div>
      {items.length > 0 ? (
        <>
          <div className="approval-list">
            {paginatedItems.map((item) => {
              if (item.type === 'task') {
                return <FollowUpCard key={`task-${item.data.id}`} task={item.data} projectId={projectId} />;
              }
              const approval = item.data;
              return (
                <article className="approval-resource-card" key={`approval-${approval.id}`}>
                  <div className="approval-resource-head"><span className="needs-type">{approval.type}</span><span className={`status-pill ${approval.status.toLowerCase()}`}>{approval.status}</span></div>
                  <div className="approval-proposal">
                    <div><h2>{approval.title}</h2><strong>{approval.quantity}</strong></div>
                    <dl className="approval-resource-details"><div><dt>Needed for</dt><dd>{approval.neededFor}</dd></div><div><dt>Needed by</dt><dd>{approval.neededBy}</dd></div></dl>
                  </div>
                  <section className="approval-reason" aria-labelledby={`reason-${approval.id}`}>
                    <h3 id={`reason-${approval.id}`}>Why OG prepared this</h3>
                    <p>{approval.reason}</p>
                  </section>
                  <p className="approval-request-meta">Requested by {approval.requestedBy} · {approval.date}</p>
                  {errors[approval.id] && <div className="approval-conflict" role="alert"><strong>{errors[approval.id]}</strong><button className="btn btn-quiet btn-small" type="button" onClick={() => void refreshApprovals()}>Refresh to see latest status</button></div>}
                  {approval.status === 'PENDING' ? (
                    <div className="approval-actions">
                      <button className="btn btn-quiet" type="button" disabled={busy === approval.id || Boolean(errors[approval.id])} onClick={() => decide(approval.id, 'REJECT')}>Reject</button>
                      <button className="btn btn-primary" type="button" disabled={busy === approval.id || Boolean(errors[approval.id])} onClick={() => decide(approval.id, 'APPROVE')}>{busy === approval.id ? 'Saving decision…' : 'Approve'}</button>
                    </div>
                  ) : <DecisionReceipt approval={approval} projectId={projectId} />}
                </article>
              );
            })}
          </div>
          <Pagination
            currentPage={page}
            totalItems={items.length}
            pageSize={pageSize}
            onPageChange={setPage}
          />
        </>
      ) : (
        <div className="empty-state">
          <span className="empty-state-icon"><ShieldCheck size={20} /></span>
          <h2>You&apos;re clear.</h2>
          <p>Nothing needs your approval right now.</p>
        </div>
      )}
    </div>
  );
}

function FollowUpCard({ task, projectId }: Readonly<{ task: Task; projectId: string }>) {
  return (
    <article className="approval-resource-card follow-up-card">
      <div className="approval-resource-head"><span className={`status-pill ${task.status.toLowerCase()}`}>{task.status.replace('_', ' ')}</span><span>{task.dueLabel}</span></div>
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
        <strong>{approval.status}</strong>
        <span>{approval.resolvedBy && approval.resolvedAt ? `by ${approval.resolvedBy} · ${approval.resolvedAt}` : 'Decision recorded'}</span>
        <p>
          {approved
            ? 'OG is resuming from the saved checkpoint.'
            : 'No supplier or external action will run.'}
        </p>
        <Link href={`/projects/${projectId}/activity`}>
          Follow in activity <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}
