import { ArrowRight, Check, ClipboardList, ShieldAlert } from 'lucide-react';
import Link from 'next/link';

type WorkflowOutcome = 'completed' | 'waiting_for_approval';

const handledSteps = [
  'Saved the site update',
  'Checked the project evidence',
  'Applied safe project changes',
  'Checked blockers and materials',
  'Updated today’s log and activity',
];

export function WorkflowReceipt({ outcome, projectId, summary, pendingActions = [] }: Readonly<{ outcome: WorkflowOutcome; projectId: string; summary?: string | null; pendingActions?: string[] }>) {
  const waiting = outcome === 'waiting_for_approval';
  return <section className={`workflow-receipt${waiting ? ' waiting' : ''}`} role="status" aria-labelledby="workflow-receipt-title">
    <div className="workflow-receipt-heading"><span className="workflow-receipt-mark" aria-hidden="true">{waiting ? <ShieldAlert size={20} /> : <ClipboardList size={20} />}</span><div><span className="workflow-receipt-kicker">{waiting ? 'SAFE HANDOFF' : 'DONE'}</span><h2 id="workflow-receipt-title">{waiting ? 'OG understood the update.' : 'OG handled it.'}</h2><p>{waiting ? 'Safe changes are saved. One decision is waiting for a manager.' : 'The project is current and every action is in the activity log.'}</p></div></div>
    {summary ? <section className="og-response-block" aria-labelledby="og-response-title"><h3 id="og-response-title">What changed</h3><p aria-label="OG response">{summary}</p></section> : null}
    <section className="og-handled-block" aria-labelledby="og-handled-title"><h3 id="og-handled-title">OG handled</h3><ul>{handledSteps.map((step) => <li key={step}><Check size={14} aria-hidden="true" />{step}</li>)}</ul></section>
    {waiting ? <section className="og-needs-you" aria-labelledby="og-needs-you-title"><span>NEEDS YOU</span><h3 id="og-needs-you-title">Manager review</h3>{pendingActions.length ? <ul aria-label="OG pending actions">{pendingActions.map((action, index) => <li key={`${index}:${action}`}>{action}</li>)}</ul> : <p>Review the saved proposal before OG continues.</p>}<Link className="btn btn-primary btn-small" href={`/projects/${projectId}/approvals`}>Review approval <ArrowRight size={14} aria-hidden="true" /></Link></section> : null}
    <div className="workflow-receipt-actions"><Link className="btn btn-quiet btn-small" href={`/projects/${projectId}/activity`}>Open activity log <ArrowRight size={14} aria-hidden="true" /></Link></div>
  </section>;
}
