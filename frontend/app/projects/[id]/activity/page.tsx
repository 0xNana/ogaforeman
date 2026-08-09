'use client';

import { AlertTriangle, ArrowRight, CheckCircle2, FileText, PackageCheck, Radio } from 'lucide-react';
import Link from 'next/link';

import { useProject } from '@/components/project-context';

export default function ActivityPage() {
  const { projectId, snapshot } = useProject();
  const activities = snapshot.activities;
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Activity</span><h1>What Oga has handled</h1><p>What happened, what changed and whether anyone needs to act.</p></div></div>
      {activities.length > 0 ? <div className="timeline">{activities.map((activity) => { const Icon = activity.kind === 'progress' ? CheckCircle2 : activity.kind === 'blocker' ? AlertTriangle : activity.kind === 'material' ? PackageCheck : FileText; return <article className="timeline-item" key={activity.id}><time>{activity.date}</time><span className={`activity-icon ${activity.kind}`}><Icon size={16} /></span><div className="timeline-copy"><h2>{activity.title}</h2><p>{activity.description}</p><div className="timeline-meta"><span>Updated by {activity.user}</span>{activity.needsAction ? <span className="status-pill requested">Needs action</span> : <span className="status-pill completed">Handled</span>}</div>{activity.needsAction && <Link className="activity-action" href={activity.kind === 'material' ? `/projects/${projectId}/approvals` : `/projects/${projectId}/tasks`}>{activity.actionLabel} <ArrowRight size={13} /></Link>}</div></article>; })}</div> : <div className="empty-state"><span className="empty-state-icon"><Radio size={20} /></span><h2>Nothing from site yet.</h2><p>Send Oga a voice note or photo when work starts moving.</p><Link href={`/projects/${projectId}/site`} className="btn btn-primary btn-small">Talk to Oga</Link></div>}
    </div>
  );
}
