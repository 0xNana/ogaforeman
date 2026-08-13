'use client';

import { AlertTriangle, Bot, CheckCircle2, ClipboardCheck, FileText, PackageCheck, Radio, UserRound } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import type { Activity, ActivityKind } from '@/lib/api';

const FILTERS = ['All', 'OG', 'Tasks', 'Issues', 'Materials', 'Approvals', 'Reports', 'People'] as const;
type ActivityFilter = (typeof FILTERS)[number];

const routes: Record<string, string> = {
  task: 'tasks', issue: 'issues', material: 'materials', material_request: 'materials',
  approval: 'approvals', report: 'reports', daily_report: 'reports', attachment: 'photos',
  site_update: 'site', project: 'overview',
};

const entityLabels: Record<string, string> = {
  task: 'Task', issue: 'Issue', material: 'Material', material_request: 'Material request',
  approval: 'Approval', report: 'Report', daily_report: 'Daily report', attachment: 'Photo',
  site_update: 'Site update', project: 'Project',
};

function matchesFilter(activity: Activity, filter: ActivityFilter) {
  if (filter === 'All') return true;
  if (filter === 'OG') return activity.actorType === 'agent' || activity.actorType === 'system';
  if (filter === 'People') return activity.actorType === 'user';
  if (filter === 'Tasks') return activity.entityType === 'task' || activity.action.startsWith('task.');
  if (filter === 'Issues') return activity.entityType === 'issue' || activity.action.startsWith('issue.');
  if (filter === 'Materials') return ['material', 'material_request'].includes(activity.entityType) || activity.action.startsWith('material.');
  if (filter === 'Approvals') return activity.entityType === 'approval' || activity.action.startsWith('approval.');
  return ['report', 'daily_report'].includes(activity.entityType) || activity.action.startsWith('report.');
}

function ActivityIcon({ kind }: { kind: ActivityKind }) {
  const Icon = kind === 'progress' ? CheckCircle2
    : kind === 'blocker' ? AlertTriangle
      : kind === 'material' ? PackageCheck
        : kind === 'approval' ? ClipboardCheck
          : kind === 'update' ? Radio : FileText;
  return <Icon aria-hidden="true" size={16} />;
}

export function ActivityStream({ activities, projectId }: { activities: Activity[]; projectId: string }) {
  const [filter, setFilter] = useState<ActivityFilter>('All');
  const filtered = useMemo(() => activities.filter((activity) => matchesFilter(activity, filter)), [activities, filter]);
  const groups = useMemo(() => {
    const result: Array<{ date: string; activities: Activity[] }> = [];
    for (const activity of filtered) {
      const current = result.at(-1);
      if (current?.date === activity.dateLabel) current.activities.push(activity);
      else result.push({ date: activity.dateLabel, activities: [activity] });
    }
    return result;
  }, [filtered]);

  return (
    <section aria-label="Project audit trail">
      <div className="activity-filters" role="group" aria-label="Filter activity">
        {FILTERS.map((option) => (
          <button key={option} type="button" className={filter === option ? 'active' : ''} aria-pressed={filter === option} onClick={() => setFilter(option)}>
            {option}
          </button>
        ))}
      </div>

      {groups.length ? (
        <div className="audit-stream">
          {groups.map((group) => (
            <section className="audit-day" key={group.date} aria-labelledby={`activity-${group.activities[0].id}`}>
              <h2 id={`activity-${group.activities[0].id}`}>{group.date}</h2>
              <ol>
                {group.activities.map((activity) => {
                  const route = routes[activity.entityType];
                  return (
                    <li key={activity.id} className="audit-entry">
                      <time dateTime={activity.occurredAt}>{activity.date}</time>
                      <span className={`activity-icon ${activity.kind}`}><ActivityIcon kind={activity.kind} /></span>
                      <div className="audit-entry-copy">
                        <h3>{activity.title}</h3>
                        {activity.description !== activity.title && <p>{activity.description}</p>}
                        <div className="audit-meta">
                          <span>{activity.actorType === 'user' ? <UserRound aria-hidden="true" size={13} /> : <Bot aria-hidden="true" size={13} />}{activity.actorType === 'user' ? 'Project member' : 'OG'}</span>
                          {route ? <Link href={`/projects/${projectId}/${route}`}>{entityLabels[activity.entityType] ?? 'Project record'}</Link> : <span>{entityLabels[activity.entityType] ?? 'Project record'}</span>}
                        </div>
                        {activity.needsAction && route && <Link className="activity-action" href={`/projects/${projectId}/${route}`}>{activity.actionLabel ?? 'Review request'}</Link>}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
        </div>
      ) : <p className="activity-filter-empty">No activity matches this filter.</p>}
    </section>
  );
}
