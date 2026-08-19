'use client';

import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api, type ProjectImportReviewRecord } from '@/lib/api';
import { PageHeader } from '@/components/page-header';

type ProjectImportReviewProps = {
  projectId: string;
  importId: string;
  onFinished: (status: 'imported' | 'cancelled') => void;
};

export function ProjectImportReview({ projectId, importId, onFinished }: Readonly<ProjectImportReviewProps>) {
  const [review, setReview] = useState<ProjectImportReviewRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<'confirm' | 'cancel' | null>(null);
  const keys = useRef({
    confirm: `project-import-confirm:${crypto.randomUUID()}`,
    cancel: `project-import-cancel:${crypto.randomUUID()}`,
  });

  const loadReview = useCallback(async () => {
    setError(null);
    try {
      setReview(await api.getProjectImport(projectId, importId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The import review could not be loaded.');
    }
  }, [importId, projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadReview());
  }, [loadReview]);

  const taskNames = useMemo(() => new Map(review?.tasks.map((task) => [task.temp_id, task.name])), [review?.tasks]);
  if (error && !review) return <ReviewState icon={<AlertTriangle />} title="We couldn’t load this import." text={error} onRetry={loadReview} />;
  if (!review) return <div className="loading-stack" aria-busy="true" aria-label="Loading import review"><p className="loading-label">Loading import review…</p><div className="loading-block loading-heading" /><div className="loading-block loading-card" /></div>;

  const isDecisionable = review.status === 'needs_review' || review.status === 'import_failed';
  const hasConflicts = review.conflicts.length > 0;
  const expectedVersion = review.version;
  const groupedRequirements = review.requirements.reduce<Map<string, typeof review.requirements>>((groups, requirement) => {
    const group = groups.get(requirement.task_temp_id) ?? [];
    group.push(requirement);
    groups.set(requirement.task_temp_id, group);
    return groups;
  }, new Map());

  async function decide(action: 'confirm' | 'cancel') {
    if (!isDecisionable || decision) return;
    setDecision(action);
    setError(null);
    try {
      const result = action === 'confirm'
        ? await api.confirmProjectImport(projectId, importId, expectedVersion, keys.current.confirm)
        : await api.cancelProjectImport(projectId, importId, expectedVersion, keys.current.cancel);
      setReview(result);
      if (result.status === 'imported' || result.status === 'cancelled') onFinished(result.status);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The import decision could not be saved.');
    } finally {
      setDecision(null);
    }
  }

  return <div className="import-review-page">
    <PageHeader eyebrow="Project setup" title="Review project initialization" description="Check what OG will create. Nothing becomes project truth until you confirm." />
    <section className="import-summary" aria-label="Import summary">
      <SummaryCount count={review.tasks.length} label="Task" />
      <SummaryCount count={review.dependencies.length} label="Dependency" />
      <SummaryCount count={review.materials.length} label="Material" />
      <SummaryCount count={review.requirements.length} label="Requirement" />
      <SummaryCount count={review.warnings.length + review.unresolved_references.length} label="Warning" />
    </section>

    {hasConflicts ? <section className="import-review-alert" role="alert" aria-labelledby="import-conflicts-title"><AlertTriangle size={20} aria-hidden="true" /><div><h2 id="import-conflicts-title">This draft can’t be initialized yet</h2><ul>{review.conflicts.map((conflict) => <li key={`${conflict.code}-${conflict.message}`}><strong>{conflict.code}</strong><span>{conflict.message}</span></li>)}</ul></div></section> : null}

    <ReviewSection title="Tasks" description="Proposed work records">
      <div className="data-table-wrapper"><table className="data-table import-review-table"><thead><tr><th>Task</th><th>Trade</th><th>Location</th><th>Planned dates</th><th>Status</th></tr></thead><tbody>{review.tasks.length ? review.tasks.map((task) => <tr key={task.temp_id}><th scope="row">{task.name}</th><td>{task.trade ?? 'Not specified'}</td><td>{task.location ?? 'Not specified'}</td><td>{dateRange(task.planned_start, task.planned_finish)}</td><td>{label(task.initial_status)}</td></tr>) : <EmptyRow columns={5} text="No tasks will be created." />}</tbody></table></div>
    </ReviewSection>

    <ReviewSection title="Dependencies" description="Work that must finish before the next task starts">
      {review.dependencies.length ? <ul className="import-dependency-list">{review.dependencies.map((dependency) => <li key={`${dependency.predecessor_temp_id}-${dependency.successor_temp_id}`}><strong>{taskNames.get(dependency.predecessor_temp_id) ?? dependency.predecessor_temp_id}</strong><span aria-hidden="true">→</span><strong>{taskNames.get(dependency.successor_temp_id) ?? dependency.successor_temp_id}</strong></li>)}</ul> : <p className="import-empty-copy">No dependencies will be created.</p>}
    </ReviewSection>

    <ReviewSection title="Materials" description="Initial inventory that OG will track">
      <div className="data-table-wrapper"><table className="data-table import-review-table"><thead><tr><th>Material</th><th>Opening stock</th><th>Unit</th><th>Location</th></tr></thead><tbody>{review.materials.length ? review.materials.map((material) => <tr key={material.temp_id}><th scope="row">{material.name}</th><td>{material.initial_on_hand_quantity}</td><td>{material.canonical_unit}</td><td>{material.location ?? 'Not specified'}</td></tr>) : <EmptyRow columns={4} text="No materials will be created." />}</tbody></table></div>
    </ReviewSection>

    <ReviewSection title="Requirements" description="Materials grouped by the task that needs them">
      {groupedRequirements.size ? <div className="import-requirement-groups">{[...groupedRequirements].map(([taskId, requirements]) => <section key={taskId}><h3>{taskNames.get(taskId) ?? taskId}</h3><ul>{requirements.map((requirement) => <li key={`${requirement.task_temp_id}-${requirement.material_temp_id}`}><strong>{review.materials.find((material) => material.temp_id === requirement.material_temp_id)?.name ?? requirement.material_temp_id}</strong><span>{requirement.required_quantity} {requirement.unit}</span><small>{requirement.required_by ? `Needed by ${requirement.required_by}` : 'Required date not specified'}</small></li>)}</ul></section>)}</div> : <p className="import-empty-copy">No task material requirements were found.</p>}
    </ReviewSection>

    <ReviewSection title="Warnings" description="Review these source details before deciding">
      {review.warnings.length || review.unresolved_references.length ? <ul className="import-warning-list">{review.warnings.map((warning) => <li key={`${warning.code}-${warning.message}`}><AlertTriangle size={18} aria-hidden="true" /><div><strong>{warning.code}</strong><p>{warning.message}</p></div></li>)}{review.unresolved_references.map((reference) => <li key={reference}><AlertTriangle size={18} aria-hidden="true" /><div><strong>UNRESOLVED_REFERENCE</strong><p>{reference}</p></div></li>)}</ul> : <p className="import-empty-copy">No warnings were found in this draft.</p>}
    </ReviewSection>

    {error ? <p className="form-error" role="alert">{error} <button className="inline-action" type="button" onClick={() => void loadReview()}>Reload review</button></p> : null}
    {isDecisionable ? <div className="import-review-actions"><button className="btn btn-quiet" type="button" disabled={decision !== null} onClick={() => void decide('cancel')}>{decision === 'cancel' ? <><Loader2 className="spinner" size={16} /> Cancelling…</> : 'Cancel Import'}</button><button className="btn btn-accent" type="button" disabled={decision !== null || hasConflicts} onClick={() => void decide('confirm')}>{decision === 'confirm' ? <><Loader2 className="spinner" size={16} /> Initializing…</> : 'Confirm & Initialize'}</button>{hasConflicts ? <p>Cancel this draft, correct the source, then start a new review.</p> : null}</div> : <ReviewState icon={review.status === 'imported' ? <CheckCircle2 /> : <XCircle />} title={review.status === 'imported' ? 'Project initialized.' : 'Import cancelled.'} text={review.status === 'imported' ? 'OG has created the reviewed project records.' : 'No canonical project records were created from this draft.'} />}
  </div>;
}

function SummaryCount({ count, label: itemLabel }: Readonly<{ count: number; label: string }>) { const label = `${count} ${itemLabel}${count === 1 ? '' : 's'}`; return <div aria-label={label}><strong>{count}</strong><span>{itemLabel}{count === 1 ? '' : 's'}</span></div>; }
function ReviewSection({ title, description, children }: Readonly<{ title: string; description: string; children: React.ReactNode }>) { return <section className="import-review-section" aria-labelledby={`review-${title.toLowerCase()}`}><header><h2 id={`review-${title.toLowerCase()}`}>{title}</h2><p>{description}</p></header>{children}</section>; }
function EmptyRow({ columns, text }: Readonly<{ columns: number; text: string }>) { return <tr><td colSpan={columns} className="secondary-cell">{text}</td></tr>; }
function ReviewState({ icon, title, text, onRetry }: Readonly<{ icon: React.ReactNode; title: string; text: string; onRetry?: () => Promise<void> }>) { return <div className="empty-state"><span className="empty-state-icon">{icon}</span><h2>{title}</h2><p>{text}</p>{onRetry ? <button className="btn btn-primary btn-small" type="button" onClick={() => void onRetry()}>Try again</button> : null}</div>; }
function dateRange(start: string | null, finish: string | null) { return start && finish ? `${start} – ${finish}` : start ?? finish ?? 'Not specified'; }
function label(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase()); }
