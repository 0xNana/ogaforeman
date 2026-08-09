'use client';

import { ApprovalList } from '@/components/approval-list';
import { useProject } from '@/components/project-context';

export default function ApprovalsPage() {
  const { projectId, snapshot, refresh } = useProject();
  return <ApprovalList approvals={snapshot.approvals} followUps={snapshot.tasks.filter((task) => task.needsAttention)} projectId={projectId} onRefresh={refresh} />;
}
