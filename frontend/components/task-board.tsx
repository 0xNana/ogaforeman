'use client';

import { ArrowRight, CircleSlash2, ListTodo, Plus, UserRound } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { api, type Task } from '@/lib/api';

type TaskFilter = 'TODAY' | 'UPCOMING' | 'BLOCKED' | 'DONE';

const filters: Array<{ label: string; value: TaskFilter }> = [
  { label: 'Today', value: 'TODAY' },
  { label: 'Upcoming', value: 'UPCOMING' },
  { label: 'Blocked', value: 'BLOCKED' },
  { label: 'Done', value: 'DONE' },
];

export function TaskBoard({ projectId, tasks, onRefresh }: Readonly<{ projectId: string; tasks: Task[]; onRefresh: () => Promise<void> }>) {
  const [filter, setFilter] = useState<TaskFilter>('TODAY');
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleTasks = useMemo(() => tasks.filter((task) => {
    if (filter === 'BLOCKED') return task.status === 'BLOCKED';
    if (filter === 'DONE') return task.status === 'COMPLETED';
    if (filter === 'UPCOMING') return task.status === 'PENDING' && !task.dueLabel.toLowerCase().includes('today');
    return task.dueLabel.toLowerCase().includes('today') || task.status === 'IN_PROGRESS' || task.status === 'BLOCKED' || task.needsAttention === true;
  }), [filter, tasks]);

  async function createTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createTask(projectId, { title: title.trim() });
      await onRefresh();
      setTitle('');
      setFilter('UPCOMING');
      setShowCreate(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The task could not be created.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Lightweight task control</span><h1>Tasks</h1><p>What is moving, what is next and what is stuck.</p></div><div className="page-heading-actions"><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add task</button><Link href={`/projects/${projectId}/site`} className="btn btn-accent btn-small">Tell Oga what changed <ArrowRight size={15} /></Link></div></div>
      <div className="resource-toolbar"><div className="filter-tabs" role="tablist" aria-label="Task views">{filters.map((item) => <button className={`filter-tab${filter === item.value ? ' active' : ''}`} type="button" role="tab" aria-selected={filter === item.value} onClick={() => setFilter(item.value)} key={item.value}>{item.label}</button>)}</div><span className="faint" style={{ fontSize: '0.78rem' }}>{visibleTasks.length} {visibleTasks.length === 1 ? 'task' : 'tasks'}</span></div>
      {visibleTasks.length > 0 ? <div className="resource-list">{visibleTasks.map((task) => <article className="resource-row" key={task.id}><div className="resource-row-main"><h2>{task.title}</h2><div className="resource-meta"><span><UserRound size={13} aria-hidden="true" /> Assigned to <strong>{task.assignee}</strong></span><span>Due <strong>{task.dueLabel}</strong></span>{task.blocking && <span>Blocking <strong>{task.blocking}</strong></span>}</div>{task.note && <p><strong>Oga note:</strong> {task.note}</p>}<div className="resource-meta"><Link className="activity-action" href={`/projects/${projectId}/site?task=${task.id}`}>{task.status === 'BLOCKED' ? 'Resolve with an update' : 'Open task'} <ArrowRight size={13} /></Link></div></div><span className={`status-pill ${task.status.toLowerCase()}`}>{task.status.replace('_', ' ')}</span></article>)}</div> : <div className="empty-state"><span className="empty-state-icon">{filter === 'BLOCKED' ? <CircleSlash2 size={20} /> : <ListTodo size={20} />}</span><h2>{filter === 'BLOCKED' ? 'Nothing blocking the site.' : 'Add the first project task.'}</h2><p>{filter === 'BLOCKED' ? 'Oga is watching for changes.' : 'Oga matches site updates to these canonical tasks before changing progress.'}</p>{filter === 'BLOCKED' ? <Link href={`/projects/${projectId}/site`} className="btn btn-primary btn-small">Talk to Oga</Link> : <button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}>Add task</button>}</div>}
      {showCreate ? <div className="modal-backdrop" role="presentation"><section className="create-project-modal" role="dialog" aria-modal="true" aria-labelledby="create-task-title"><button className="modal-close" type="button" onClick={() => setShowCreate(false)} aria-label="Close">×</button><span className="eyebrow">Project setup</span><h2 id="create-task-title">Add a task Oga can recognize.</h2><form className="auth-form" onSubmit={createTask}><label>Task name<input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={300} placeholder="First-floor blockwork" /></label>{error ? <p role="alert">{error}</p> : null}<button className="btn btn-primary btn-block" type="submit" disabled={submitting}>{submitting ? 'Adding…' : 'Add task'}</button></form></section></div> : null}
    </div>
  );
}
