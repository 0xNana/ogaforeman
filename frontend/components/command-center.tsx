'use client';

import { AlertTriangle, ArrowRight, Camera, CheckCircle2, CircleDot, ClipboardList, FileText, MessageSquareText, Mic, Package } from 'lucide-react';
import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { PageHeader } from '@/components/page-header';
import type { ProjectSnapshot, Task } from '@/lib/api';

export function CommandCenter({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSetup = searchParams?.get('setup') === '1';

  useEffect(() => {
    if (!isSetup) return;
    if (snapshot.tasks.length === 0) router.push(`/projects/${snapshot.project.id}/tasks?setup=1`);
    else if (snapshot.materials.length === 0) router.push(`/projects/${snapshot.project.id}/materials?setup=1`);
    else router.replace(`/projects/${snapshot.project.id}`);
  }, [isSetup, snapshot.project.id, snapshot.tasks.length, snapshot.materials.length, router]);

  if (isSetup && (snapshot.tasks.length === 0 || snapshot.materials.length === 0)) {
    return <div className="loading-stack" aria-busy="true"><div className="loading-block loading-heading" /></div>;
  }

  const completed = snapshot.tasks.filter((task) => task.status === 'COMPLETED').length;
  const blockers = snapshot.tasks.filter((task) => task.status === 'BLOCKED');
  const pendingApprovals = snapshot.approvals.filter((approval) => approval.status === 'PENDING');
  const lowMaterials = snapshot.materials.filter((material) => material.status === 'LOW' || material.status === 'DELAYED');
  const followUps = snapshot.tasks.filter((task) => task.needsAttention && task.status !== 'BLOCKED');
  const progress = snapshot.tasks.length === 0 ? 0 : Math.round((completed / snapshot.tasks.length) * 100);
  const atRisk = new Set(blockers.flatMap((task) => task.blocking ? [task.blocking] : [])).size;
  const insight = getInsight(snapshot);

  return (
    <div>
      <MobileFieldHome snapshot={snapshot} />
      <div className="desktop-overview">
        <PageHeader
          eyebrow={snapshot.project.name}
          title="Project overview"
          description={`${snapshot.project.location} · ${formatStatus(snapshot.project.status)}`}
          actions={<Link href={`/projects/${snapshot.project.id}/reports`} className="btn btn-quiet btn-small"><FileText size={15} aria-hidden="true" /> Daily report</Link>}
        />

      {snapshot.report.date === 'No report yet' ? <FirstSiteSetup snapshot={snapshot} /> : null}

      <dl className="overview-status" aria-label="Project status metrics">
        <Metric label="Overall progress" value={`${progress}%`} />
        <Metric label="Target completion" value="Not set" />
        <Metric label="Open issues" value={String(blockers.length)} tone={blockers.length ? 'warning' : undefined} />
        <Metric label="Work at risk" value={String(atRisk)} tone={atRisk ? 'danger' : undefined} />
      </dl>

      <div className="overview-grid">
        <section className="overview-section" aria-labelledby="attention-title">
          <SectionHeading id="attention-title" title="Needs Attention" meta={`${blockers.length + lowMaterials.length + pendingApprovals.length + followUps.length} open`} />
          <div className="attention-list">
            {blockers.map((task) => <AttentionRow key={task.id} type="Blocker" title={task.title} detail={task.blocking ? `${task.blocking} is at risk.` : task.note || 'This task is blocked.'} href={`/projects/${snapshot.project.id}/tasks`} />)}
            {lowMaterials.map((material) => <AttentionRow key={material.id} type="Material" title={material.name} detail={`${material.quantity} ${material.unit} recorded; ${material.need} needed for ${material.forWork}.`} href={`/projects/${snapshot.project.id}/materials`} />)}
            {pendingApprovals.map((approval) => <AttentionRow key={approval.id} type="Approval" title={approval.title} detail={`${approval.quantity} · Needed ${approval.neededBy}`} href={`/projects/${snapshot.project.id}/approvals`} />)}
            {followUps.map((task) => <AttentionRow key={task.id} type="Follow-up" title={task.title} detail={`Assigned to ${task.assignee}.`} href={`/projects/${snapshot.project.id}/tasks`} />)}
            {!blockers.length && !lowMaterials.length && !pendingApprovals.length && !followUps.length ? <p className="overview-empty">Nothing needs attention.</p> : null}
          </div>
        </section>

        <Today snapshot={snapshot} />
      </div>

      <Lookahead projectId={snapshot.project.id} tasks={snapshot.tasks} />

      <aside className="og-noticed" aria-label="OG noticed">
        <span>OG noticed</span>
        <p>{insight}</p>
      </aside>
      </div>
    </div>
  );
}

function MobileFieldHome({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const blockers = snapshot.tasks.filter((task) => task.status === 'BLOCKED');
  const lowMaterials = snapshot.materials.filter((material) => material.status === 'LOW' || material.status === 'DELAYED');
  const approvals = snapshot.approvals.filter((approval) => approval.status === 'PENDING');
  const attentionCount = blockers.length + lowMaterials.length + approvals.length;
  const openOg = () => window.dispatchEvent(new Event('og:open'));

  return (
    <section className="mobile-field-home" aria-labelledby="mobile-field-title">
      <header>
        <span className="eyebrow">{snapshot.report.date === 'No report yet' ? 'Today' : snapshot.report.date}</span>
        <h1 id="mobile-field-title">{snapshot.project.name}</h1>
        <p>{attentionCount ? `${attentionCount} thing${attentionCount === 1 ? '' : 's'} need attention` : 'Site is clear right now'}</p>
      </header>

      {attentionCount ? <div className="mobile-field-attention" aria-label="Site attention">
        {blockers.map((task) => <Link href={`/projects/${snapshot.project.id}/tasks`} key={task.id}><AlertTriangle size={20} aria-hidden="true" /><span><strong>{task.title}</strong><small>{task.note || 'Work is blocked'}</small></span><ArrowRight size={17} aria-hidden="true" /></Link>)}
        {lowMaterials.map((material) => <Link href={`/projects/${snapshot.project.id}/materials`} key={material.id}><Package size={20} aria-hidden="true" /><span><strong>{material.name} running low</strong><small>{material.quantity} {material.unit} recorded</small></span><ArrowRight size={17} aria-hidden="true" /></Link>)}
        {approvals.map((approval) => <Link href={`/projects/${snapshot.project.id}/approvals`} key={approval.id}><CircleDot size={20} aria-hidden="true" /><span><strong>{approval.title}</strong><small>Manager decision needed</small></span><ArrowRight size={17} aria-hidden="true" /></Link>)}
      </div> : null}

      <button className="mobile-talk-og" type="button" onClick={openOg}><span><Mic size={28} aria-hidden="true" /></span><strong>Talk to OG</strong><small>Voice, text, photo or file</small></button>
      <button className="mobile-add-photos" type="button" onClick={openOg}><Camera size={20} aria-hidden="true" /> Add site photos</button>

      <section className="mobile-today" aria-labelledby="mobile-today-title">
        <div><h2 id="mobile-today-title">Today</h2><Link href={`/projects/${snapshot.project.id}/tasks`}>All tasks <ArrowRight size={15} aria-hidden="true" /></Link></div>
        {[...snapshot.report.completed.map((item) => ({ item, state: 'complete' as const })), ...snapshot.report.inProgress.map((item) => ({ item, state: 'progress' as const }))].map(({ item, state }) => <p key={`${state}-${item}`}><span className={state}>{state === 'complete' ? <CheckCircle2 size={20} aria-hidden="true" /> : <ArrowRight size={20} aria-hidden="true" />}</span><strong>{item}</strong></p>)}
        {!snapshot.report.completed.length && !snapshot.report.inProgress.length ? <p className="mobile-today-empty">No work reported yet.</p> : null}
      </section>
    </section>
  );
}

function Metric({ label, value, tone }: Readonly<{ label: string; value: string; tone?: 'warning' | 'danger' }>) {
  return <div className={tone ? `overview-metric ${tone}` : 'overview-metric'}><dt>{label}</dt><dd>{value}</dd></div>;
}

function SectionHeading({ id, title, meta }: Readonly<{ id: string; title: string; meta: string }>) {
  return <div className="overview-section-heading"><h2 id={id}>{title}</h2><span>{meta}</span></div>;
}

function AttentionRow({ type, title, detail, href }: Readonly<{ type: string; title: string; detail: string; href: string }>) {
  return <article className="attention-row"><AlertTriangle size={17} aria-hidden="true" /><div><span>{type}</span><h3>{title}</h3><p>{detail}</p></div><Link href={href} aria-label={`Review ${title}`}>Review <ArrowRight size={14} aria-hidden="true" /></Link></article>;
}

function Today({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const groups = [
    ['Completed', snapshot.report.completed],
    ['In progress', snapshot.report.inProgress],
    ['Blockers', snapshot.report.blocked],
    ['Materials & deliveries', snapshot.report.materials],
    ['Next up', snapshot.report.tomorrow],
  ] as const;
  const hasWork = groups.some(([, items]) => items.length > 0);
  return <section className="overview-section" aria-labelledby="today-title"><SectionHeading id="today-title" title="Today" meta={snapshot.report.date} />{hasWork ? <div className="today-register">{groups.map(([label, items]) => items.length ? <div className="today-group" key={label}><h3>{label}</h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></div> : null)}</div> : <p className="overview-empty">No work has been reported for today.</p>}</section>;
}

function Lookahead({ projectId, tasks }: Readonly<{ projectId: string; tasks: Task[] }>) {
  return <section className="lookahead-section" aria-labelledby="lookahead-title"><SectionHeading id="lookahead-title" title="Two-Week Lookahead" meta={`${tasks.length} activities`} />{tasks.length ? <><div className="lookahead-table-wrapper"><table className="lookahead-table"><thead><tr><th>Activity</th><th>Start</th><th>Finish</th><th>Progress</th><th>Status</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.id}><th scope="row"><Link href={`/projects/${projectId}/tasks`}>{task.title}</Link></th><td>{task.startLabel || 'Not set'}</td><td>{task.dueLabel || 'Not set'}</td><td>{taskProgress(task)}</td><td><span className={`status-pill ${task.status.toLowerCase()}`}>{formatStatus(task.status)}</span></td></tr>)}</tbody></table></div><p className="lookahead-note">Showing recorded tasks. Start dates and numeric progress appear only when project records provide them.</p></> : <p className="overview-empty">No tasks are available for the lookahead.</p>}</section>;
}

function taskProgress(task: Task) {
  if (task.status === 'COMPLETED') return '100%';
  if (task.status === 'PENDING') return '0%';
  return 'Not reported';
}

function getInsight(snapshot: ProjectSnapshot) {
  const blockedDependency = snapshot.tasks.find((task) => task.status === 'BLOCKED' && task.blocking);
  if (blockedDependency) return `${blockedDependency.title} is blocking ${blockedDependency.blocking}.`;
  const lowMaterial = snapshot.materials.find((material) => material.status === 'LOW' || material.status === 'DELAYED');
  if (lowMaterial) return `${lowMaterial.name} is below or behind the recorded project requirement.`;
  const approval = snapshot.approvals.find((item) => item.status === 'PENDING');
  if (approval) return `${approval.title} is waiting for a decision.`;
  return 'No immediate project exception is visible in the current records.';
}

function formatStatus(status: string) {
  return status.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase());
}

function FirstSiteSetup({ snapshot }: Readonly<{ snapshot: ProjectSnapshot }>) {
  const steps = [
    { complete: snapshot.tasks.length > 0, description: 'Add the jobs and milestones OG should recognize in site updates.', href: `/projects/${snapshot.project.id}/tasks`, icon: ClipboardList, label: 'Add your first task' },
    { complete: snapshot.materials.length > 0, description: 'Record stock names, units and minimum quantities before reporting usage.', href: `/projects/${snapshot.project.id}/materials`, icon: Package, label: 'Add project materials' },
    { complete: false, description: 'Tell OG what happened today by text, voice, photo or file.', href: `/projects/${snapshot.project.id}/site`, icon: MessageSquareText, label: 'Send the first site update' },
  ];
  return <section className="first-site-setup" aria-labelledby="first-site-title"><div className="first-site-intro"><span className="eyebrow">Start here</span><h2 id="first-site-title">Set up your first site.</h2><p>Give OG enough project context to recognize what your team reports and follow through safely.</p></div><ol className="first-site-steps">{steps.map(({ complete, description, href, icon: Icon, label }, index) => <li className={complete ? 'complete' : undefined} key={label}><span className="first-site-step-number" aria-hidden="true">{complete ? <CheckCircle2 size={18} /> : index + 1}</span><span className="first-site-step-copy"><strong>{label}</strong><span>{description}</span></span><Link className="btn btn-quiet btn-small" href={href}>{complete ? 'Review' : label} <ArrowRight size={14} aria-hidden="true" /></Link></li>)}</ol></section>;
}
