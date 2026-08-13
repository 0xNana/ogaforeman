'use client';

import { Download, FileClock, Pencil, Search, Share2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/page-header';
import { api, type DailyLog } from '@/lib/api';

export function DailyLogRegister({ projectName, projectId, logs, onRefresh }: Readonly<{ projectName: string; projectId: string; logs: DailyLog[]; onRefresh: () => Promise<void> }>) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(logs[0]?.id ?? null);
  const [editing, setEditing] = useState(false);
  const [summary, setSummary] = useState('');
  const [crew, setCrew] = useState('');
  const [weather, setWeather] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const visible = useMemo(() => { const needle = query.trim().toLowerCase(); return logs.filter((log) => !needle || [log.date, log.summary, ...log.completed, ...log.blocked].some((value) => value.toLowerCase().includes(needle))); }, [logs, query]);
  const selected = visible.find((log) => log.id === selectedId) ?? visible[0] ?? null;

  function beginEdit(log: DailyLog) { setSummary(log.summary); setCrew(log.crew ?? ''); setWeather(log.weather ?? ''); setEditing(true); setMessage(null); }
  async function save(event: React.FormEvent) { event.preventDefault(); if (!selected) return; setSaving(true); setMessage(null); try { await api.editDailyLog(projectId, selected.id, { summary: summary.trim(), crew_summary: crew.trim(), weather_summary: weather.trim(), expected_version: selected.version }); await onRefresh(); setEditing(false); setMessage('Daily log updated.'); } catch (cause) { setMessage(cause instanceof Error ? cause.message : 'The daily log could not be updated.'); } finally { setSaving(false); } }
  async function share(log: DailyLog) { const text = `${projectName} — ${log.date}\n${log.summary}`; try { if (navigator.share) await navigator.share({ title: `${projectName} daily log`, text }); else { await navigator.clipboard.writeText(text); setMessage('Daily log copied to the clipboard.'); } } catch (cause) { if (cause instanceof DOMException && cause.name === 'AbortError') return; setMessage('The daily log could not be shared.'); } }

  return <div><PageHeader eyebrow="Site record" title="Daily Logs" description="Client-ready daily records compiled from persisted site updates." />
    <div className="daily-log-layout"><aside className="daily-log-index" aria-label="Daily log dates"><label className="register-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search daily logs</span><input type="search" placeholder="Search daily logs" value={query} onChange={(event) => setQuery(event.target.value)} /></label>{visible.map((log) => <button className={selected?.id === log.id ? 'active' : ''} type="button" onClick={() => { setSelectedId(log.id); setEditing(false); setMessage(null); }} key={log.id}><strong>{log.date}</strong><span>{log.summary}</span></button>)}{!visible.length ? <div className="daily-log-index-empty"><FileClock size={20} aria-hidden="true" /><strong>No matching daily logs.</strong><span>Change the search to review another date.</span></div> : null}</aside>
      {selected ? <article className="daily-log-paper"><header><div><span className="report-mark">OG Foreman · {projectName}</span><h2>{selected.date}</h2><p>{selected.summary}</p></div><span className={`status-pill ${selected.status.toLowerCase()}`}>{selected.status.toLowerCase()}</span></header><div className="daily-log-actions"><button className="btn btn-quiet btn-small" type="button" aria-label="Edit daily log" onClick={() => beginEdit(selected)}><Pencil size={14} aria-hidden="true" /> Edit</button><button className="btn btn-quiet btn-small" type="button" aria-label="Share daily log" onClick={() => void share(selected)}><Share2 size={14} aria-hidden="true" /> Share</button><button className="btn btn-primary btn-small" type="button" aria-label="Export daily log" onClick={() => window.print()}><Download size={14} aria-hidden="true" /> Export</button></div>{message ? <p className="status-banner info" role="status">{message}</p> : null}{editing ? <form className="daily-log-edit" onSubmit={(event) => void save(event)}><label>Summary<textarea value={summary} onChange={(event) => setSummary(event.target.value)} required maxLength={20000} /></label><label>Crew<input value={crew} onChange={(event) => setCrew(event.target.value)} maxLength={5000} placeholder="Not recorded" /></label><label>Weather<input value={weather} onChange={(event) => setWeather(event.target.value)} maxLength={5000} placeholder="Not recorded" /></label><div><button className="btn btn-quiet" type="button" onClick={() => setEditing(false)} disabled={saving}>Cancel</button><button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save log'}</button></div></form> : <DailyLogBody log={selected} />}</article> : <div className="empty-state daily-log-empty"><span className="empty-state-icon"><FileClock size={20} aria-hidden="true" /></span><h2>No matching daily logs.</h2><p>Daily logs appear here after persisted site updates produce a report.</p></div>}
    </div>
  </div>;
}

function DailyLogBody({ log }: Readonly<{ log: DailyLog }>) {
  const sections = [['Work completed', log.completed], ['Work in progress', log.inProgress], ['Delays / blockers', log.blocked], ['Materials', log.materials], ['Deliveries', log.deliveries], ['Inspections', log.inspections], ['Photos', log.photos], ['Tomorrow', log.tomorrow], ['Risks', log.risks]] as const;
  return <><dl className="daily-log-context"><div><dt>Crew</dt><dd>{log.crew || 'Not recorded'}</dd></div><div><dt>Weather</dt><dd>{log.weather || 'Not recorded'}</dd></div></dl><div className="daily-log-sections">{sections.map(([title, items]) => <section key={title}><h3>{title}</h3>{items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Nothing recorded.</p>}</section>)}</div><footer><span>Compiled by OG from {log.sourceUpdateCount} site {log.sourceUpdateCount === 1 ? 'update' : 'updates'}</span><span>{log.status === 'PUBLISHED' ? 'Published' : 'Draft'}</span></footer></>;
}
