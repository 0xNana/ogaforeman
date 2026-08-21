import { AlertTriangle } from 'lucide-react';

import type { ProjectImportReviewRecord } from '@/lib/api';

export function ProjectImportDraftDetails({ review }: Readonly<{ review: ProjectImportReviewRecord }>) {
  const taskNames = new Map(review.tasks.map((task) => [task.temp_id, task.name]));
  const groupedRequirements = review.requirements.reduce<Map<string, typeof review.requirements>>((groups, requirement) => {
    const group = groups.get(requirement.task_temp_id) ?? [];
    group.push(requirement);
    groups.set(requirement.task_temp_id, group);
    return groups;
  }, new Map());

  return (
    <>
      {review.status === 'validation_failed' ? (
        <StatusBanner
          title="OG found an issue in the extracted plan."
          text={review.retryable
            ? 'Your original file is saved. Retry extraction so OG can rebuild the draft without uploading it again.'
            : 'Review the items below. Nothing will be added to the project unless the draft passes validation.'}
        />
      ) : null}
      {review.status === 'import_failed' ? (
        <StatusBanner
          title="Initialization did not finish."
          text={review.failure_message ?? 'The reviewed draft is still available and can be retried safely.'}
        />
      ) : null}

      <section className="import-summary" aria-label="Import summary">
        <SummaryCount count={review.tasks.length} label="Task" />
        <SummaryCount count={review.dependencies.length} label="Dependency" />
        <SummaryCount count={review.materials.length} label="Material" />
        <SummaryCount count={review.requirements.length} label="Requirement" />
        <SummaryCount count={review.warnings.length + review.unresolved_references.length} label="Warning" />
      </section>

      {review.project ? (
        <ReviewSection title="Project details" description="These reviewed details will identify the project">
          <dl className="import-project-details">
            <ProjectDetail label="Name" value={review.project.name} />
            <ProjectDetail label="Location" value={review.project.location ?? 'Not specified'} />
            <ProjectDetail label="Type" value={review.project.type ?? 'Not specified'} />
            <ProjectDetail label="Status" value={label(review.project.status)} />
            <ProjectDetail label="Start" value={formatDate(review.project.start_date)} />
            <ProjectDetail label="Target finish" value={formatDate(review.project.target_end_date)} />
          </dl>
          {review.project.description ? <p className="import-project-description">{review.project.description}</p> : null}
        </ReviewSection>
      ) : null}

      {review.conflicts.length ? (
        <section className="import-review-alert" role="alert" aria-labelledby="import-conflicts-title">
          <AlertTriangle size={20} aria-hidden="true" />
          <div>
            <h2 id="import-conflicts-title">What needs attention</h2>
            <ul>{review.conflicts.map((conflict) => <li key={`${conflict.code}-${conflict.message}`}><span>{conflictMessage(conflict, taskNames)}</span></li>)}</ul>
          </div>
        </section>
      ) : null}

      <ReviewSection title="Tasks" description="Proposed work records">
        <div className="data-table-wrapper" tabIndex={0} aria-label="Scrollable tasks table"><table className="data-table import-review-table"><thead><tr><th>Task</th><th>Trade</th><th>Location</th><th>Planned dates</th><th>Status</th></tr></thead><tbody>{review.tasks.length ? review.tasks.map((task) => <tr key={task.temp_id}><th scope="row">{task.name}</th><td>{task.trade ?? 'Not specified'}</td><td>{task.location ?? 'Not specified'}</td><td>{dateRange(task.planned_start, task.planned_finish)}</td><td>{label(task.initial_status)}</td></tr>) : <EmptyRow columns={5} text="No tasks will be created." />}</tbody></table></div>
      </ReviewSection>

      <ReviewSection title="Dependencies" description="Work that must finish before the next task starts">
        {review.dependencies.length ? <ul className="import-dependency-list">{review.dependencies.map((dependency) => <li key={`${dependency.predecessor_temp_id}-${dependency.successor_temp_id}`}><strong>{taskNames.get(dependency.predecessor_temp_id) ?? humanizeReference(dependency.predecessor_temp_id)}</strong><span aria-hidden="true">→</span><strong>{taskNames.get(dependency.successor_temp_id) ?? humanizeReference(dependency.successor_temp_id)}</strong></li>)}</ul> : <p className="import-empty-copy">No dependencies will be created.</p>}
      </ReviewSection>

      <ReviewSection title="Materials" description="Initial inventory that OG will track">
        <div className="data-table-wrapper" tabIndex={0} aria-label="Scrollable materials table"><table className="data-table import-review-table"><thead><tr><th>Material</th><th>Opening stock</th><th>Unit</th><th>Location</th></tr></thead><tbody>{review.materials.length ? review.materials.map((material) => <tr key={material.temp_id}><th scope="row">{material.name}</th><td>{material.initial_on_hand_quantity}</td><td>{material.canonical_unit}</td><td>{material.location ?? 'Not specified'}</td></tr>) : <EmptyRow columns={4} text="No materials will be created." />}</tbody></table></div>
      </ReviewSection>

      <ReviewSection title="Requirements" description="Materials grouped by the task that needs them">
        {groupedRequirements.size ? <div className="import-requirement-groups">{[...groupedRequirements].map(([taskId, requirements]) => <section key={taskId}><h3>{taskNames.get(taskId) ?? taskId}</h3><ul>{requirements.map((requirement) => <li key={`${requirement.task_temp_id}-${requirement.material_temp_id}`}><strong>{review.materials.find((material) => material.temp_id === requirement.material_temp_id)?.name ?? requirement.material_temp_id}</strong><span>{requirement.required_quantity} {requirement.unit}</span><small>{requirement.required_by ? `Needed by ${requirement.required_by}` : 'Required date not specified'}</small></li>)}</ul></section>)}</div> : <p className="import-empty-copy">No task material requirements were found.</p>}
      </ReviewSection>

      <ReviewSection title="Warnings" description="Review these source details before deciding">
        {review.warnings.length || review.unresolved_references.length ? <ul className="import-warning-list">{review.warnings.map((warning) => <li key={`${warning.code}-${warning.message}`}><AlertTriangle size={18} aria-hidden="true" /><div><strong>{warning.code}</strong><p>{warning.message}</p></div></li>)}{review.unresolved_references.map((reference) => <li key={reference}><AlertTriangle size={18} aria-hidden="true" /><div><strong>UNRESOLVED_REFERENCE</strong><p>{reference}</p></div></li>)}</ul> : <p className="import-empty-copy">No warnings were found in this draft.</p>}
      </ReviewSection>
    </>
  );
}

function StatusBanner({ title, text }: Readonly<{ title: string; text: string }>) {
  return <section className="import-lifecycle-banner error" role="alert"><AlertTriangle aria-hidden="true" /><div><h2>{title}</h2><p>{text}</p></div></section>;
}

function SummaryCount({ count, label: itemLabel }: Readonly<{ count: number; label: string }>) { const text = `${count} ${itemLabel}${count === 1 ? '' : 's'}`; return <div aria-label={text}><strong>{count}</strong><span>{itemLabel}{count === 1 ? '' : 's'}</span></div>; }
function ReviewSection({ title, description, children }: Readonly<{ title: string; description: string; children: React.ReactNode }>) { const id = `review-${title.toLowerCase()}`; return <section className="import-review-section" aria-labelledby={id}><header><h2 id={id}>{title}</h2><p>{description}</p></header>{children}</section>; }
function EmptyRow({ columns, text }: Readonly<{ columns: number; text: string }>) { return <tr><td colSpan={columns} className="secondary-cell">{text}</td></tr>; }
function ProjectDetail({ label: detailLabel, value }: Readonly<{ label: string; value: string }>) { return <div><dt>{detailLabel}</dt><dd>{value}</dd></div>; }
function dateRange(start: string | null, finish: string | null) { return start && finish ? `${start} – ${finish}` : start ?? finish ?? 'Not specified'; }
function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat('en', { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)) : 'Not specified'; }
function label(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase()); }

function humanizeReference(value: string): string {
  const words = value.replace(/^tmp_(task|material|phase)_/, '').replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function conflictMessage(
  conflict: ProjectImportReviewRecord['conflicts'][number],
  taskNames: Map<string, string>,
): string {
  if (conflict.code === 'UNKNOWN_PREDECESSOR') {
    const reference = conflict.message.split(':').at(-1)?.trim() ?? '';
    return `OG found “${taskNames.get(reference) ?? humanizeReference(reference)}” as a prerequisite, but it was not included as a task in this draft.`;
  }
  if (conflict.code === 'UNKNOWN_SUCCESSOR') {
    const reference = conflict.message.split(':').at(-1)?.trim() ?? '';
    return `OG found a dependency leading to “${taskNames.get(reference) ?? humanizeReference(reference)}”, but that task was not included in this draft.`;
  }
  return conflict.message;
}
