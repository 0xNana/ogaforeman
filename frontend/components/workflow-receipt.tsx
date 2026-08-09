import {
  ArrowRight,
  Check,
  Circle,
  ClipboardList,
  ShieldAlert,
} from 'lucide-react';
import Link from 'next/link';

type WorkflowOutcome = 'completed' | 'waiting_for_approval';

const handledSteps = [
  'Update received',
  'Evidence understood',
  'Safe project changes applied',
  'Blockers and materials checked',
  'Follow-through created where needed',
  'Activity log updated',
];

export function WorkflowReceipt({
  outcome,
  projectId,
  summary,
  pendingActions = [],
}: Readonly<{
  outcome: WorkflowOutcome;
  projectId: string;
  summary?: string | null;
  pendingActions?: string[];
}>) {
  const waiting = outcome === 'waiting_for_approval';

  return (
    <section
      className={`workflow-receipt${waiting ? ' waiting' : ''}`}
      role="status"
      aria-labelledby="workflow-receipt-title"
    >
      <div className="workflow-receipt-heading">
        <span className="workflow-receipt-mark" aria-hidden="true">
          {waiting ? <ShieldAlert size={20} /> : <ClipboardList size={20} />}
        </span>
        <div>
          <span className="workflow-receipt-kicker">
            {waiting ? 'Safe handoff' : 'Update handled'}
          </span>
          <h2 id="workflow-receipt-title">
            {waiting ? 'Oga understood the update.' : 'Oga handled it.'}
          </h2>
          <p>
            {waiting
              ? 'Safe changes are saved. One decision is waiting for a manager.'
              : 'The project is current and every action is in the activity log.'}
          </p>
        </div>
      </div>

      {summary && <p className="workflow-receipt-response" aria-label="Oga response">{summary}</p>}
      {pendingActions.length > 0 && (
        <ul className="workflow-receipt-pending" aria-label="Oga pending actions">
          {pendingActions.map((action, index) => <li key={`${index}:${action}`}>{action}</li>)}
        </ul>
      )}

      <ol className="workflow-receipt-steps" aria-label="Oga workflow progress">
        {handledSteps.map((label, index) => {
          const isApproval = waiting && index === 4;
          const isResume = waiting && index === 5;
          return (
            <li className={isApproval ? 'current' : isResume ? 'upcoming' : 'complete'} key={label}>
              <span className="workflow-step-marker" aria-hidden="true">
                {isApproval || isResume ? <Circle size={14} /> : <Check size={14} />}
              </span>
              <span>{isApproval ? 'Manager approval required' : isResume ? 'Resume from saved checkpoint' : label}</span>
            </li>
          );
        })}
      </ol>

      <div className="workflow-receipt-actions">
        {waiting && (
          <Link className="btn btn-primary btn-small" href={`/projects/${projectId}/approvals`}>
            Review approval <ArrowRight size={14} />
          </Link>
        )}
        <Link className="btn btn-quiet btn-small" href={`/projects/${projectId}/activity`}>
          Open activity log <ArrowRight size={14} />
        </Link>
      </div>
    </section>
  );
}
