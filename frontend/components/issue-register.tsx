'use client';

import { MessageSquareWarning, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/page-header';
import { RecordDetails, RecordDrawer } from '@/components/record-drawer';
import type { Issue, Task } from '@/lib/api';

export function IssueRegister({ issues, tasks }: Readonly<{ issues: Issue[]; tasks: Task[] }>) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('OPEN');
  const [selected, setSelected] = useState<Issue | null>(null);
  const taskNames = new Map(tasks.map((task) => [task.id, task.title]));
  const visible = useMemo(() => issues.filter((issue) => {
    const statusMatch = status === 'ALL' || issue.status === status;
    const needle = query.trim().toLowerCase();
    return statusMatch && (!needle || [issue.id, issue.description, issue.type, issue.owner].some((value) => value.toLowerCase().includes(needle)));
  }), [issues, query, status]);

  return <div><PageHeader eyebrow="Issue log" title="Issues" description="Track blockers, safety, quality, schedule risk, and site observations." />
    <div className="register-toolbar"><label className="register-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search issues</span><input type="search" placeholder="Search issues, owners, or IDs" value={query} onChange={(event) => setQuery(event.target.value)} /></label><div className="filter-tabs" aria-label="Issue filters">{['OPEN', 'ACKNOWLEDGED', 'MITIGATED', 'RESOLVED', 'ALL'].map((item) => <button className={`filter-tab${status === item ? ' active' : ''}`} type="button" aria-pressed={status === item} onClick={() => setStatus(item)} key={item}>{format(item)}</button>)}</div><span className="register-count">{visible.length} {visible.length === 1 ? 'issue' : 'issues'}</span></div>
    {visible.length ? <div className="data-table-wrapper"><table className="data-table register-table"><thead><tr><th>ID</th><th>Issue</th><th>Type</th><th>Location</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead><tbody>{visible.map((issue) => <tr key={issue.id}><td className="secondary-cell">{issue.id}</td><th scope="row"><button className="register-row-link" type="button" onClick={() => setSelected(issue)}>{issue.description}</button></th><td>{format(issue.type)}</td><td>{issue.location || 'Not recorded'}</td><td>{issue.owner}</td><td>{issue.dueLabel}</td><td><span className={`status-pill ${issue.status.toLowerCase()}`}>{format(issue.status)}</span></td></tr>)}</tbody></table></div> : <div className="empty-state"><span className="empty-state-icon"><MessageSquareWarning size={20} aria-hidden="true" /></span><h2>{issues.length ? 'No matching issues.' : 'Nothing blocking the site.'}</h2><p>{issues.length ? 'Change the search or filter. New issue records appear here when site evidence creates them.' : 'OG is watching for changes.'}</p></div>}
    {selected ? <RecordDrawer eyebrow={`Issue · ${selected.id}`} title={selected.description} onClose={() => setSelected(null)}><span className={`status-pill ${selected.status.toLowerCase()}`}>{format(selected.status)}</span><RecordDetails items={[{ label: 'Description', value: selected.description }, { label: 'Status', value: format(selected.status) }, { label: 'Severity', value: format(selected.severity) }, { label: 'Type', value: format(selected.type) }, { label: 'Location', value: selected.location || 'Not recorded' }, { label: 'Responsible person', value: selected.owner }, { label: 'Due', value: selected.dueLabel }, { label: 'Linked task', value: selected.taskIds.length ? selected.taskIds.map((id) => taskNames.get(id) || id).join(', ') : 'None recorded' }, { label: 'Linked material', value: 'Not available in this projection' }, { label: 'Linked photos', value: 'Not available in this projection' }, { label: 'Source', value: selected.evidenceRefs.join(', ') || 'None recorded' }, { label: 'Activity history', value: 'Open Activity for the project audit trail' }]} /></RecordDrawer> : null}
  </div>;
}

function format(value: string) { return value.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase()); }
