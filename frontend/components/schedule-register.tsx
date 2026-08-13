'use client';

import { CalendarDays, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/page-header';
import { RecordDetails, RecordDrawer } from '@/components/record-drawer';
import type { Task } from '@/lib/api';

type View = 'LIST' | 'GANTT';
type Filter = 'ALL' | 'ACTIVE' | 'BLOCKED' | 'AT_RISK' | 'MILESTONES';

export function ScheduleRegister({ tasks }: Readonly<{ tasks: Task[] }>) {
  const [view, setView] = useState<View>('LIST');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Task | null>(null);
  const names = new Map(tasks.map((task) => [task.id, task.title]));
  const visible = useMemo(() => tasks.filter((task) => matches(task, filter, query)), [filter, query, tasks]);

  return <div><PageHeader eyebrow="Project planning" title="Schedule" description="Review dated work, dependencies, milestones, and downstream schedule risk." />
    <div className="schedule-controls"><div className="filter-tabs" aria-label="Schedule view"><button className={`filter-tab${view === 'LIST' ? ' active' : ''}`} type="button" aria-pressed={view === 'LIST'} onClick={() => setView('LIST')}>List</button><button className={`filter-tab${view === 'GANTT' ? ' active' : ''}`} type="button" aria-pressed={view === 'GANTT'} onClick={() => setView('GANTT')}>Gantt</button></div><label className="register-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search schedule</span><input type="search" placeholder="Search activities, trades, or assignees" value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
    <div className="register-toolbar schedule-filters"><div className="filter-tabs" aria-label="Schedule filters">{(['ALL', 'ACTIVE', 'BLOCKED', 'AT_RISK', 'MILESTONES'] as Filter[]).map((item) => <button className={`filter-tab${filter === item ? ' active' : ''}`} type="button" aria-pressed={filter === item} onClick={() => setFilter(item)} key={item}>{format(item)}</button>)}</div><span className="register-count">{visible.length} activities</span></div>
    {visible.length ? view === 'LIST' ? <ScheduleList tasks={visible} onSelect={setSelected} /> : <Gantt tasks={visible} onSelect={setSelected} /> : <div className="empty-state"><span className="empty-state-icon"><CalendarDays size={20} aria-hidden="true" /></span><h2>No matching schedule activities.</h2><p>Change the search or filter to see other project work.</p></div>}
    {selected ? <RecordDrawer eyebrow={`Activity · ${selected.id}`} title={selected.title} onClose={() => setSelected(null)}><span className={`status-pill ${selected.atRisk ? 'delayed' : selected.status.toLowerCase()}`}>{selected.atRisk ? 'At risk' : format(selected.status)}</span><RecordDetails items={[{ label: 'Trade', value: selected.trade || 'Not recorded' }, { label: 'Start', value: selected.startLabel || 'Not set' }, { label: 'Finish', value: finishLabel(selected) }, { label: 'Duration', value: selected.durationDays ? `${selected.durationDays} day${selected.durationDays === 1 ? '' : 's'}` : 'Not available' }, { label: 'Progress', value: selected.progress == null ? 'Not reported' : `${selected.progress}%` }, { label: 'Milestone', value: selected.isMilestone ? 'Yes' : 'No' }, { label: 'Dependencies', value: linkedNames(selected.dependencyIds, names) }, { label: 'Blocking / downstream impact', value: linkedNames(selected.downstreamIds, names) }, { label: 'Blocker', value: selected.status === 'BLOCKED' ? selected.note || 'Blocked' : 'None recorded' }, { label: 'Source', value: selected.sourceRefs?.join(', ') || 'None recorded' }]} /></RecordDrawer> : null}
  </div>;
}

function ScheduleList({ tasks, onSelect }: Readonly<{ tasks: Task[]; onSelect: (task: Task) => void }>) {
  return <div className="data-table-wrapper"><table className="data-table register-table"><thead><tr><th>Activity</th><th>Trade</th><th>Start</th><th>Finish</th><th>Duration</th><th>Progress</th><th>Status</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.id}><th scope="row"><button className="register-row-link" type="button" onClick={() => onSelect(task)}>{task.isMilestone ? '◆ ' : ''}{task.title}</button></th><td>{task.trade || 'Not recorded'}</td><td>{task.startLabel || 'Not set'}</td><td>{finishLabel(task)}</td><td>{task.durationDays ? `${task.durationDays}d` : 'Not available'}</td><td>{task.progress == null ? 'Not reported' : `${task.progress}%`}</td><td><span className={`status-pill ${task.atRisk ? 'delayed' : task.status.toLowerCase()}`}>{task.atRisk ? 'At risk' : format(task.status)}</span></td></tr>)}</tbody></table></div>;
}

function Gantt({ tasks, onSelect }: Readonly<{ tasks: Task[]; onSelect: (task: Task) => void }>) {
  const dated = tasks.filter((task) => task.startDate && task.finishDate);
  const unscheduled = tasks.filter((task) => !task.startDate || !task.finishDate);
  if (!dated.length) return <div className="empty-state"><span className="empty-state-icon"><CalendarDays size={20} aria-hidden="true" /></span><h2>No dated activities.</h2><p>Use List view to review the unscheduled tasks already recorded.</p></div>;
  const dates = dated.flatMap((task) => [day(task.startDate!), day(task.finishDate!)]);
  const first = Math.min(...dates); const last = Math.max(...dates); const span = Math.max(1, last - first + 86_400_000);
  return <div className="gantt-wrapper" aria-label="Schedule timeline"><div className="gantt-range"><span>{displayDate(first)}</span><span>{displayDate(last)}</span></div>{dated.map((task) => { const start = day(task.startDate!); const finish = day(task.finishDate!); const left = ((start - first) / span) * 100; const width = Math.max(2, ((finish - start + 86_400_000) / span) * 100); return <div className="gantt-row" key={task.id}><button type="button" className="gantt-label" onClick={() => onSelect(task)}>{task.title}</button><div className="gantt-track"><button type="button" className={`gantt-bar ${task.isMilestone ? 'milestone' : ''} ${task.atRisk ? 'risk' : ''} ${task.status.toLowerCase()}`} style={{ left: `${left}%`, width: `${width}%` }} aria-label={`${task.title}, ${task.startLabel} to ${finishLabel(task)}`} onClick={() => onSelect(task)}><span>{task.progress ?? 0}%</span></button></div></div>;})}{unscheduled.length ? <p className="gantt-unscheduled">{unscheduled.length} unscheduled {unscheduled.length === 1 ? 'activity is' : 'activities are'} available in List view.</p> : null}</div>;
}

function matches(task: Task, filter: Filter, query: string) {
  if (filter === 'ACTIVE' && !['PENDING', 'IN_PROGRESS'].includes(task.status)) return false;
  if (filter === 'BLOCKED' && task.status !== 'BLOCKED') return false;
  if (filter === 'AT_RISK' && !task.atRisk) return false;
  if (filter === 'MILESTONES' && !task.isMilestone) return false;
  const needle = query.trim().toLowerCase();
  return !needle || [task.id, task.title, task.trade, task.assignee].some((value) => value?.toLowerCase().includes(needle));
}
function linkedNames(ids: string[] | undefined, names: Map<string, string>) { return ids?.length ? ids.map((id) => names.get(id) || id).join(', ') : 'None recorded'; }
function finishLabel(task: Task) { return task.finishDate ? new Date(`${task.finishDate}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : 'Not set'; }
function day(value: string) { return new Date(`${value}T00:00:00Z`).getTime(); }
function displayDate(value: number) { return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }); }
function format(value: string) { return value.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase()); }
