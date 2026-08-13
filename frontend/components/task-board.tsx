'use client';

import { ArrowRight, ListTodo, Plus, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { PageHeader } from '@/components/page-header';
import { Pagination } from '@/components/pagination';
import { RecordDetails, RecordDrawer } from '@/components/record-drawer';
import { TaskCreateDialog } from '@/components/task-create-dialog';
import type { Task } from '@/lib/api';

type TaskFilter = 'ALL' | 'MINE' | 'DUE_SOON' | 'BLOCKED' | 'COMPLETED';
const filters: Array<{ label: string; value: TaskFilter }> = [
  { label: 'All', value: 'ALL' }, { label: 'My work', value: 'MINE' },
  { label: 'Due soon', value: 'DUE_SOON' }, { label: 'Blocked', value: 'BLOCKED' },
  { label: 'Completed', value: 'COMPLETED' },
];

export function TaskBoard({ projectId, tasks, viewerId, onRefresh }: Readonly<{ projectId: string; tasks: Task[]; viewerId: string | null; onRefresh: () => Promise<void> }>) {
  const isSetup = useSearchParams()?.get('setup') === '1';
  const [filter, setFilter] = useState<TaskFilter>('ALL');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Task | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const visible = useMemo(() => tasks.filter((task) => matchesTask(task, filter, query, viewerId)), [filter, query, tasks, viewerId]);
  const pageSize = 15;
  const rows = visible.slice((page - 1) * pageSize, page * pageSize);
  const taskNames = new Map(tasks.map((task) => [task.id, task.title]));

  function changeFilter(next: TaskFilter) { setFilter(next); setPage(1); }
  return <div><PageHeader eyebrow="Work register" title="Tasks" description="Search the project work plan, inspect dependencies, and act on blocked work." actions={<><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} aria-hidden="true" /> Add task</button>{isSetup && tasks.length ? <Link href={`/projects/${projectId}?setup=1`} className="btn btn-accent btn-small">Next step <ArrowRight size={15} aria-hidden="true" /></Link> : null}</>} />
    <div className="register-toolbar"><label className="register-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search tasks</span><input type="search" placeholder="Search tasks, assignees, or IDs" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></label><div className="filter-tabs" aria-label="Task filters">{filters.map((item) => <button className={`filter-tab${filter === item.value ? ' active' : ''}`} type="button" aria-pressed={filter === item.value} onClick={() => changeFilter(item.value)} key={item.value}>{item.label}</button>)}</div><span className="register-count">{visible.length} {visible.length === 1 ? 'task' : 'tasks'}</span></div>
    {visible.length ? <><div className="data-table-wrapper"><table className="data-table register-table"><thead><tr><th>ID</th><th>Task</th><th>Location</th><th>Trade</th><th>Assignee</th><th>Start</th><th>Due</th><th>Progress</th><th>Status</th></tr></thead><tbody>{rows.map((task) => <tr key={task.id}><td className="secondary-cell">{task.id}</td><th scope="row"><button className="register-row-link" type="button" onClick={() => setSelected(task)}>{task.title}</button></th><td>{task.location || 'Not recorded'}</td><td>{task.trade || 'Not recorded'}</td><td>{task.assignee}</td><td>{task.startLabel || 'Not set'}</td><td>{task.dueLabel}</td><td>{task.progress ?? 'Not reported'}{task.progress != null ? '%' : ''}</td><td><span className={`status-pill ${task.status.toLowerCase()}`}>{format(task.status)}</span></td></tr>)}</tbody></table></div><Pagination currentPage={page} totalItems={visible.length} pageSize={pageSize} onPageChange={setPage} /></> : <div className="empty-state"><span className="empty-state-icon"><ListTodo size={20} aria-hidden="true" /></span><h2>No matching tasks.</h2><p>Change the search or filter to see other project work.</p></div>}
    {selected ? <RecordDrawer eyebrow={`Task · ${selected.id}`} title={selected.title} onClose={() => setSelected(null)}><span className={`status-pill ${selected.status.toLowerCase()}`}>{format(selected.status)}</span><RecordDetails items={[{ label: 'Location', value: selected.location || 'Not recorded' }, { label: 'Trade', value: selected.trade || 'Not recorded' }, { label: 'Assignee', value: selected.assignee }, { label: 'Start', value: selected.startLabel || 'Not set' }, { label: 'Due', value: selected.dueLabel }, { label: 'Progress', value: selected.progress == null ? 'Not reported' : `${selected.progress}%` }, { label: 'Dependencies', value: selected.dependencyIds?.length ? selected.dependencyIds.map((id) => taskNames.get(id) || id).join(', ') : 'None recorded' }, { label: 'Blocker', value: selected.blocking || selected.note || 'None recorded' }, { label: 'Linked issue', value: selected.sourceRefs?.find((ref) => ref.startsWith('iss_')) || 'None recorded' }, { label: 'Linked photos', value: 'Not available in this projection' }, { label: 'Source update', value: selected.sourceRefs?.find((ref) => ref.startsWith('sup_')) || 'None recorded' }, { label: 'Activity', value: 'Open Activity for the project audit trail' }]} /></RecordDrawer> : null}
    {showCreate ? <TaskCreateDialog projectId={projectId} onClose={() => setShowCreate(false)} onRefresh={onRefresh} onSuccess={() => setFilter('ALL')} /> : null}
  </div>;
}

function matchesTask(task: Task, filter: TaskFilter, query: string, viewerId: string | null) {
  if (filter === 'MINE' && (!viewerId || task.assignee !== viewerId)) return false;
  if (filter === 'BLOCKED' && task.status !== 'BLOCKED') return false;
  if (filter === 'COMPLETED' && task.status !== 'COMPLETED') return false;
  if (filter === 'DUE_SOON' && !/today|tomorrow|overdue|due/i.test(task.dueLabel)) return false;
  const needle = query.trim().toLowerCase();
  return !needle || [task.id, task.title, task.assignee, task.location, task.trade].some((value) => value?.toLowerCase().includes(needle));
}

function format(value: string) { return value.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase()); }
