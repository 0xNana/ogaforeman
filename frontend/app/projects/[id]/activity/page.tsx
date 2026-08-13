'use client';

import { AlertTriangle, ArrowRight, CheckCircle2, FileText, PackageCheck, Radio } from 'lucide-react';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { useProject } from '@/components/project-context';
import { Pagination } from '@/components/pagination';

export default function ActivityPage() {
  const { projectId, snapshot } = useProject();
  const activities = snapshot.activities;
  const [page, setPage] = useState(1);
  const pageSize = 15;
  const paginatedActivities = useMemo(() => {
    return activities.slice((page - 1) * pageSize, page * pageSize);
  }, [activities, page, pageSize]);

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Activity</span>
          <h1>What OG has handled</h1>
          <p>What happened, what changed and whether anyone needs to act.</p>
        </div>
      </div>
      {activities.length > 0 ? (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}></th>
                <th style={{ width: '100px' }}>Time</th>
                <th>Activity</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {paginatedActivities.map((activity) => {
                const Icon = activity.kind === 'progress' ? CheckCircle2 : activity.kind === 'blocker' ? AlertTriangle : activity.kind === 'material' ? PackageCheck : FileText;
                return (
                  <tr key={activity.id}>
                    <td>
                      <span className={`activity-icon ${activity.kind}`} style={{ width: 28, height: 28, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Icon size={14} />
                      </span>
                    </td>
                    <td className="secondary-cell" style={{ whiteSpace: 'nowrap' }}>{activity.date}</td>
                    <td>
                      <div className="primary-cell" style={{ marginBottom: '4px' }}>{activity.title}</div>
                      <div className="secondary-cell" style={{ whiteSpace: 'normal', lineHeight: 1.4 }}>{activity.description}</div>
                      {activity.needsAction && (
                        <div style={{ marginTop: '8px' }}>
                          <Link className="activity-action" style={{ fontSize: '0.75rem', display: 'inline-flex', padding: '4px 8px', background: 'var(--surface)', borderRadius: '6px', border: '1px solid var(--line)' }} href={activity.kind === 'material' ? `/projects/${projectId}/approvals` : `/projects/${projectId}/tasks`}>
                            {activity.actionLabel} <ArrowRight size={13} />
                          </Link>
                        </div>
                      )}
                    </td>
                    <td>
                      {activity.needsAction ? <span className="status-pill requested" style={{ whiteSpace: 'nowrap' }}>Needs action</span> : <span className="status-pill completed" style={{ whiteSpace: 'nowrap' }}>Handled</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <Pagination
            currentPage={page}
            totalItems={activities.length}
            pageSize={pageSize}
            onPageChange={setPage}
          />
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-state-icon"><Radio size={20} /></span>
          <h2>Nothing from site yet.</h2>
          <p>Send OG a voice note or photo when work starts moving.</p>
          <Link href={`/projects/${projectId}/site`} className="btn btn-primary btn-small">Talk to OG</Link>
        </div>
      )}
    </div>
  );
}
