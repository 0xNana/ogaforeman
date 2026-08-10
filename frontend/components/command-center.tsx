'use client';

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock3,
  FileText,
  MessageSquareText,
  Package,
  PackageCheck,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import type { ProjectSnapshot } from '@/lib/api';

const ACTIVITY_PAGE_SIZE = 5;

export function CommandCenter({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const [activityPage, setActivityPage] = useState(1);
  const completedCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'COMPLETED').length, [snapshot.tasks]);
  const attentionCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'BLOCKED' || task.needsAttention).length + snapshot.approvals.filter((approval) => approval.status === 'PENDING').length, [snapshot.approvals, snapshot.tasks]);
  const waitingCount = useMemo(() => snapshot.tasks.filter((task) => task.status === 'PENDING').length, [snapshot.tasks]);
  const pendingApprovals = snapshot.approvals.filter((approval) => approval.status === 'PENDING');
  const blockers = snapshot.tasks.filter((task) => task.status === 'BLOCKED');
  const followUps = snapshot.tasks.filter((task) => task.needsAttention);
  const activityPageCount = Math.max(1, Math.ceil(snapshot.activities.length / ACTIVITY_PAGE_SIZE));
  const currentActivityPage = Math.min(activityPage, activityPageCount);
  const visibleActivities = snapshot.activities.slice(
    (currentActivityPage - 1) * ACTIVITY_PAGE_SIZE,
    currentActivityPage * ACTIVITY_PAGE_SIZE,
  );
  const needsFirstSiteSetup = snapshot.report.date === 'No report yet';

  return (
    <div>
      <div className="page-heading">
        <div><span className="eyebrow">{snapshot.project.location}</span><h1>{snapshot.project.name}</h1><p>Good morning. Here&apos;s what is happening on site.</p></div>
        <div className="page-heading-actions"><Link href={`/projects/${snapshot.project.id}/reports`} className="btn btn-quiet btn-small"><FileText size={15} /> Daily report</Link></div>
      </div>

      {needsFirstSiteSetup ? <FirstSiteSetup snapshot={snapshot} /> : null}

      <div className="app-grid">
        <div>
          <div className="stats-row" aria-label="Today summary"><div className="stat-card"><span className="stat-card-label">Completed</span><span className="stat-card-value">{completedCount}</span></div><div className="stat-card warning"><span className="stat-card-label">Needs attention</span><span className="stat-card-value">{attentionCount}</span></div><div className="stat-card waiting"><span className="stat-card-label">Waiting</span><span className="stat-card-value">{waitingCount}</span></div></div>

          <section className="app-card feed-card" aria-labelledby="today-title">
            <div className="card-heading"><h2 id="today-title">Today</h2><span>{snapshot.activities.length} updates</span></div>
            <div className="activity-list">{visibleActivities.map((activity) => <ActivityItem key={activity.id} activity={activity} />)}</div>
            {activityPageCount > 1 ? (
              <nav className="dashboard-pagination" aria-label="Dashboard activity pages">
                <button
                  className="btn btn-quiet btn-small"
                  type="button"
                  aria-label="Previous activity page"
                  disabled={currentActivityPage === 1}
                  onClick={() => setActivityPage(currentActivityPage - 1)}
                >
                  <ChevronLeft size={15} aria-hidden="true" /> Previous
                </button>
                <span aria-live="polite">Page {currentActivityPage} of {activityPageCount}</span>
                <button
                  className="btn btn-quiet btn-small"
                  type="button"
                  aria-label="Next activity page"
                  disabled={currentActivityPage === activityPageCount}
                  onClick={() => setActivityPage(currentActivityPage + 1)}
                >
                  Next <ChevronRight size={15} aria-hidden="true" />
                </button>
              </nav>
            ) : null}
          </section>
        </div>

        <aside className="needs-column" aria-labelledby="needs-title"><div className="needs-heading"><h2 id="needs-title">Needs you</h2><span>{pendingApprovals.length + blockers.length + followUps.length} open</span></div>{pendingApprovals.map((approval) => <div className="needs-card material" key={approval.id}><span className="needs-type">Approval</span><h3>{approval.title}</h3><p>{approval.quantity} · Needed {approval.neededBy}</p><Link href={`/projects/${snapshot.project.id}/approvals`} className="btn btn-primary btn-small btn-block">Review <ArrowRight size={14} /></Link></div>)}{blockers.map((task) => <div className="needs-card blocker" key={task.id}><span className="needs-type">Blocker</span><h3>{task.title}</h3><p>{task.blocking ? `${task.blocking} is at risk.` : task.note}</p><Link href={`/projects/${snapshot.project.id}/tasks`} className="btn btn-quiet btn-small btn-block">Review blocker <ArrowRight size={14} /></Link></div>)}{followUps.map((task) => <div className="needs-card blocker" key={task.id}><span className="needs-type">Follow-up</span><h3>{task.title}</h3><p>Assigned to {task.assignee}.</p><Link href={`/projects/${snapshot.project.id}/tasks`} className="btn btn-quiet btn-small btn-block">Open follow-up <ArrowRight size={14} /></Link></div>)}{pendingApprovals.length === 0 && blockers.length === 0 && followUps.length === 0 && <div className="clear-card"><strong>You&apos;re clear.</strong><p>Oga will let you know when something needs you.</p></div>}<div className="app-card app-card-pad"><span className="needs-type">Oga&apos;s brief</span><h3 style={{ marginTop: '12px', fontSize: '1.05rem' }}>The day is moving.</h3><p style={{ marginTop: '8px', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>Blockwork is done. Electrical work needs a follow-up. Cement is the next decision.</p><Link href={`/projects/${snapshot.project.id}/reports`} className="activity-action">Open today&apos;s report <ArrowRight size={13} /></Link></div></aside>
      </div>
    </div>
  );
}

function FirstSiteSetup({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const steps = [
    {
      complete: snapshot.tasks.length > 0,
      description: 'Add the jobs and milestones Oga should recognize in site updates.',
      href: `/projects/${snapshot.project.id}/tasks`,
      icon: ClipboardList,
      label: 'Add your first task',
    },
    {
      complete: snapshot.materials.length > 0,
      description: 'Record stock names, units and minimum quantities before reporting usage.',
      href: `/projects/${snapshot.project.id}/materials`,
      icon: Package,
      label: 'Add project materials',
    },
    {
      complete: false,
      description: 'Tell Oga what happened today by text, voice, photo or file.',
      href: `/projects/${snapshot.project.id}/site`,
      icon: MessageSquareText,
      label: 'Send the first site update',
    },
  ];

  return (
    <section className="first-site-setup" aria-labelledby="first-site-title">
      <div className="first-site-intro">
        <span className="eyebrow">Start here</span>
        <h2 id="first-site-title">Set up your first site.</h2>
        <p>Give Oga enough project context to recognize what your team reports and follow through safely.</p>
      </div>
      <ol className="first-site-steps">
        {steps.map(({ complete, description, href, icon: Icon, label }, index) => (
          <li className={complete ? 'complete' : undefined} key={label}>
            <span className="first-site-step-number" aria-hidden="true">{complete ? <CheckCircle2 size={18} /> : index + 1}</span>
            <span className="first-site-step-copy"><strong>{label}</strong><span>{description}</span></span>
            <Link className="btn btn-quiet btn-small" href={href}>{complete ? 'Review' : label} <ArrowRight size={14} aria-hidden="true" /></Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ActivityItem({ activity }: Readonly<{ activity: ProjectSnapshot['activities'][number] }>) {
  const Icon = activity.kind === 'progress' ? CheckCircle2 : activity.kind === 'blocker' ? AlertTriangle : activity.kind === 'material' ? PackageCheck : activity.kind === 'report' ? FileText : Clock3;
  return <article className="activity-item"><span className={`activity-icon ${activity.kind}`}><Icon size={16} aria-hidden="true" /></span><div><h3>{activity.title}</h3><p>{activity.description}</p>{activity.needsAction && <span className="activity-action">{activity.actionLabel} <ArrowRight size={13} /></span>}</div><span className="activity-time">{activity.date}</span></article>;
}
