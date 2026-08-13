'use client';

import { Radio } from 'lucide-react';
import Link from 'next/link';
import { ActivityStream } from '@/components/activity-stream';
import { useProject } from '@/components/project-context';

export default function ActivityPage() {
  const { projectId, snapshot } = useProject();
  const activities = snapshot.activities;

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Activity</span>
          <h1>Activity</h1>
          <p>A chronological audit trail of project actions and state changes.</p>
        </div>
      </div>
      {activities.length > 0 ? (
        <ActivityStream activities={activities} projectId={projectId} />
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
