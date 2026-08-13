'use client';

import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useProject } from '@/components/project-context';

const MAX_TASK_ROWS = 20;
const COMMON_TASKS = [
  'Site clearance',
  'Excavation',
  'Foundation concrete',
  'Ground floor slab',
  'First floor blockwork',
  'Roofing',
  'Plumbing first fix',
  'Electrical first fix',
  'Plastering',
  'Painting',
  'Floor tiling'
];

type TaskDraft = {
  key: number;
  title: string;
  isCustom?: boolean;
  trade: string;
  location: string;
  assigneeId: string;
  plannedStart: string;
  plannedEnd: string;
};

type TaskCreateDialogProps = {
  projectId: string;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onSuccess?: () => void;
};

function emptyTask(key: number): TaskDraft {
  return { key, title: '', isCustom: false, trade: '', location: '', assigneeId: '', plannedStart: '', plannedEnd: '' };
}

export function TaskCreateDialog({ projectId, onClose, onRefresh, onSuccess }: Readonly<TaskCreateDialogProps>) {
  const { snapshot } = useProject();
  const nextKey = useRef(2);
  const firstTitleInput = useRef<HTMLInputElement>(null);
  const firstSelectInput = useRef<HTMLSelectElement>(null);
  const [rows, setRows] = useState<TaskDraft[]>([emptyTask(1)]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    firstTitleInput.current?.focus();
    firstSelectInput.current?.focus();
  }, []);

  function updateRow(key: number, update: Partial<TaskDraft>) {
    setRows((current) => current.map((row) => (
      row.key === key ? { ...row, ...update } : row
    )));
  }

  function addRow() {
    setRows((current) => [...current, emptyTask(nextKey.current++)]);
  }

  function removeRow(key: number) {
    setRows((current) => current.filter((row) => row.key !== key));
  }

  async function createTasks(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const createdKeys: number[] = [];

    try {
      for (const row of rows) {
        if (!row.title.trim()) continue;
        await api.createTask(projectId, {
          title: row.title.trim(),
          trade: row.trade.trim() || undefined,
          location: row.location.trim() || undefined,
          assigned_to: row.assigneeId || undefined,
          planned_start: row.plannedStart ? `${row.plannedStart}T00:00:00Z` : undefined,
          planned_end: row.plannedEnd ? `${row.plannedEnd}T23:59:59Z` : undefined,
        });
        createdKeys.push(row.key);
      }
      await onRefresh();
      onSuccess?.();
      onClose();
    } catch (cause) {
      if (createdKeys.length > 0) {
        setRows((current) => current.filter((row) => !createdKeys.includes(row.key)));
        await onRefresh();
      }
      const message = cause instanceof Error
        ? cause.message
        : 'The tasks could not be created.';
      setError(createdKeys.length > 0
        ? `${createdKeys.length} task${createdKeys.length === 1 ? '' : 's'} added. ${message}`
        : message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="create-project-modal material-create-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-task-title"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !submitting) onClose();
        }}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Close" disabled={submitting}>
          ×
        </button>
        <span className="eyebrow">Project setup</span>
        <h2 id="create-task-title">Add tasks OG can track.</h2>
        <p className="material-create-intro">
          Add up to {MAX_TASK_ROWS} tasks, then save them together.
        </p>
        <form className="auth-form material-create-form" onSubmit={createTasks}>
          <div className="material-entry-list">
            {rows.map((row, index) => {
              const position = index + 1;
              return (
                <fieldset className="material-entry" key={row.key} disabled={submitting}>
                  <legend className="sr-only">Task {position}</legend>
                  <div className="material-entry-heading">
                    <span className="material-entry-title" aria-hidden="true">Task {position}</span>
                    {rows.length > 1 ? (
                      <button
                        className="material-remove-button"
                        type="button"
                        onClick={() => removeRow(row.key)}
                        aria-label={`Remove task ${position}`}
                      >
                        <Trash2 size={14} aria-hidden="true" /> Remove
                      </button>
                    ) : null}
                  </div>
                  <label style={{ display: 'block', marginTop: '12px' }}>
                    Task name
                    {row.isCustom ? (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <input
                          ref={index === 0 ? firstTitleInput : undefined}
                          aria-label={`Custom task name ${position}`}
                          value={row.title}
                          onChange={(event) => updateRow(row.key, { title: event.target.value })}
                          required
                          maxLength={300}
                          placeholder="Type custom task name"
                          autoFocus
                        />
                        <button
                          type="button"
                          className="btn btn-quiet"
                          onClick={() => updateRow(row.key, { isCustom: false, title: '' })}
                        >
                          Back
                        </button>
                      </div>
                    ) : (
                      <select
                        ref={index === 0 ? firstSelectInput : undefined}
                        aria-label={`Task name ${position}`}
                        value={COMMON_TASKS.includes(row.title) ? row.title : (row.title ? 'custom' : '')}
                        onChange={(event) => {
                          if (event.target.value === 'custom') {
                            updateRow(row.key, { isCustom: true, title: '' });
                          } else {
                            updateRow(row.key, { title: event.target.value });
                          }
                        }}
                        required
                      >
                        <option value="" disabled>Select a task...</option>
                        {COMMON_TASKS.map((t) => <option key={t} value={t}>{t}</option>)}
                        <option value="custom">Other (type your own)...</option>
                      </select>
                    )}
                  </label>
                  <div className="task-operational-fields">
                    <label>Trade<input value={row.trade} onChange={(event) => updateRow(row.key, { trade: event.target.value })} maxLength={200} placeholder="Electrical" /></label>
                    <label>Location<input value={row.location} onChange={(event) => updateRow(row.key, { location: event.target.value })} maxLength={500} placeholder="First floor" /></label>
                    <label>Assignee<select value={row.assigneeId} onChange={(event) => updateRow(row.key, { assigneeId: event.target.value })}><option value="">Unassigned</option>{(snapshot.members ?? []).map((member) => <option value={member.id} key={member.id}>{member.displayName}</option>)}</select></label>
                    <label>Start<input type="date" value={row.plannedStart} onChange={(event) => updateRow(row.key, { plannedStart: event.target.value })} /></label>
                    <label>Finish<input type="date" min={row.plannedStart || undefined} value={row.plannedEnd} onChange={(event) => updateRow(row.key, { plannedEnd: event.target.value })} /></label>
                  </div>
                </fieldset>
              );
            })}
          </div>
          {rows.length < MAX_TASK_ROWS ? (
            <button
              className="btn btn-quiet btn-small material-add-row"
              type="button"
              onClick={addRow}
              disabled={submitting}
            >
              <Plus size={15} aria-hidden="true" /> Add another task
            </button>
          ) : null}
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
            {submitting
              ? `Adding ${rows.length} task${rows.length === 1 ? '' : 's'}…`
              : `Add ${rows.length} task${rows.length === 1 ? '' : 's'}`}
          </button>
        </form>
      </section>
    </div>
  );
}
