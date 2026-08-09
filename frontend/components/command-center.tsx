'use client';

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  Image as ImageIcon,
  LoaderCircle,
  Mic,
  Paperclip,
  PackageCheck,
  Send,
  Type,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { api, type ProjectSnapshot } from '@/lib/api';

type ComposerState = 'idle' | 'recording' | 'processing' | 'success' | 'error';

export function CommandCenter({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const [text, setText] = useState('');
  const [composerState, setComposerState] = useState<ComposerState>('idle');
  const [error, setError] = useState<string | null>(null);

  const completedCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'COMPLETED').length, [snapshot.tasks]);
  const attentionCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'BLOCKED' || task.needsAttention).length + snapshot.approvals.filter((approval) => approval.status === 'PENDING').length, [snapshot.approvals, snapshot.tasks]);
  const waitingCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'PENDING').length, [snapshot.tasks]);
  const pendingApprovals = snapshot.approvals.filter((approval) => approval.status === 'PENDING');
  const blockers = snapshot.tasks.filter((task) => task.status === 'BLOCKED');
  const followUps = snapshot.tasks.filter((task) => task.needsAttention);

  async function submitUpdate() {
    if (!text.trim() || composerState === 'processing') return;
    setComposerState('processing');
    setError(null);
    try {
      const result = await api.submitSiteUpdate(snapshot.project.id, text);
      if (result.status !== 'queued') {
        setComposerState('error');
        setError('Oga could not queue that update.');
        return;
      }
      setComposerState('success');
      setText('');
    } catch {
      setComposerState('error');
      setError('Oga could not reach the project. Check your connection and try again.');
    }
  }

  function toggleRecording() {
    setError(null);
    setComposerState((current) => current === 'recording' ? 'idle' : 'recording');
  }

  return (
    <div>
      <div className="page-heading">
        <div><span className="eyebrow">{snapshot.project.location}</span><h1>{snapshot.project.name}</h1><p>Good morning. Here&apos;s what is happening on site.</p></div>
        <div className="page-heading-actions"><Link href={`/projects/${snapshot.project.id}/reports`} className="btn btn-quiet btn-small"><FileText size={15} /> Daily report</Link><Link href={`/projects/${snapshot.project.id}/site`} className="btn btn-accent btn-small"><Mic size={15} /> Site update</Link></div>
      </div>

      <div className="app-grid">
        <div>
          <section className="app-card composer-card" aria-labelledby="composer-title">
            <span className="composer-kicker">Talk to Oga</span>
            <h2 id="composer-title">What&apos;s happening on site?</h2>
            <textarea aria-label="Site update" value={text} onChange={(event) => setText(event.target.value)} placeholder="Tell Oga what happened..." disabled={composerState === 'processing'} />
            {composerState === 'recording' && <div className="recording-bar" role="status"><span>Listening... 00:14</span><span className="waveform" aria-hidden="true">{Array.from({ length: 12 }, (_, index) => <span key={index} style={{ height: `${8 + (index % 4) * 4}px` }} />)}</span></div>}
            {composerState === 'processing' && <div className="status-banner info" role="status"><LoaderCircle size={16} className="spin-icon" /> Oga is checking the project...</div>}
            {composerState === 'success' && <div className="status-banner success" role="status"><CheckCircle2 size={16} /> Oga handled it. Your update is in the queue.</div>}
            {composerState === 'error' && <div className="status-banner error" role="alert"><AlertTriangle size={16} /> {error}</div>}
            <div className="composer-actions"><div className="composer-tools"><button className="tool-button" type="button" onClick={toggleRecording}><Mic size={15} /> {composerState === 'recording' ? 'Stop' : 'Talk'}</button><button className="tool-button" type="button"><ImageIcon size={15} /> Photos</button><button className="tool-button" type="button"><Paperclip size={15} /> Attach</button><button className="tool-button" type="button"><Type size={15} /> Type</button></div><button className="talk-button" type="button" onClick={submitUpdate} disabled={!text.trim() || composerState === 'processing'}><Send size={15} /> Send update</button></div>
          </section>

          <div className="stats-row" aria-label="Today summary"><div className="stat-card"><span className="stat-card-label">Completed</span><span className="stat-card-value">{completedCount}</span></div><div className="stat-card warning"><span className="stat-card-label">Needs attention</span><span className="stat-card-value">{attentionCount}</span></div><div className="stat-card waiting"><span className="stat-card-label">Waiting</span><span className="stat-card-value">{waitingCount}</span></div></div>

          <section className="app-card feed-card" aria-labelledby="today-title"><div className="card-heading"><h2 id="today-title">Today</h2><span>{snapshot.activities.length} updates</span></div><div className="activity-list">{snapshot.activities.map((activity) => <ActivityItem key={activity.id} activity={activity} />)}</div></section>
        </div>

        <aside className="needs-column" aria-labelledby="needs-title"><div className="needs-heading"><h2 id="needs-title">Needs you</h2><span>{pendingApprovals.length + blockers.length + followUps.length} open</span></div>{pendingApprovals.map((approval) => <div className="needs-card material" key={approval.id}><span className="needs-type">Approval</span><h3>{approval.title}</h3><p>{approval.quantity} · Needed {approval.neededBy}</p><Link href={`/projects/${snapshot.project.id}/approvals`} className="btn btn-primary btn-small btn-block">Review <ArrowRight size={14} /></Link></div>)}{blockers.map((task) => <div className="needs-card blocker" key={task.id}><span className="needs-type">Blocker</span><h3>{task.title}</h3><p>{task.blocking ? `${task.blocking} is at risk.` : task.note}</p><Link href={`/projects/${snapshot.project.id}/tasks`} className="btn btn-quiet btn-small btn-block">Review blocker <ArrowRight size={14} /></Link></div>)}{followUps.map((task) => <div className="needs-card blocker" key={task.id}><span className="needs-type">Follow-up</span><h3>{task.title}</h3><p>Assigned to {task.assignee}.</p><Link href={`/projects/${snapshot.project.id}/tasks`} className="btn btn-quiet btn-small btn-block">Open follow-up <ArrowRight size={14} /></Link></div>)}{pendingApprovals.length === 0 && blockers.length === 0 && followUps.length === 0 && <div className="clear-card"><strong>You&apos;re clear.</strong><p>Oga will let you know when something needs you.</p></div>}<div className="app-card app-card-pad"><span className="needs-type">Oga&apos;s brief</span><h3 style={{ marginTop: '12px', fontSize: '1.05rem' }}>The day is moving.</h3><p style={{ marginTop: '8px', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>Blockwork is done. Electrical work needs a follow-up. Cement is the next decision.</p><Link href={`/projects/${snapshot.project.id}/reports`} className="activity-action">Open today&apos;s report <ArrowRight size={13} /></Link></div></aside>
      </div>
    </div>
  );
}

function ActivityItem({ activity }: Readonly<{ activity: ProjectSnapshot['activities'][number] }>) {
  const Icon = activity.kind === 'progress' ? CheckCircle2 : activity.kind === 'blocker' ? AlertTriangle : activity.kind === 'material' ? PackageCheck : activity.kind === 'report' ? FileText : Clock3;
  return <article className="activity-item"><span className={`activity-icon ${activity.kind}`}><Icon size={16} aria-hidden="true" /></span><div><h3>{activity.title}</h3><p>{activity.description}</p>{activity.needsAction && <span className="activity-action">{activity.actionLabel} <ArrowRight size={13} /></span>}</div><span className="activity-time">{activity.date}</span></article>;
}
