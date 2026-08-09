'use client';

import { ApprovalList } from '@/components/approval-list';
import { useProject } from '@/components/project-context';

export default function ApprovalsPage() {
  const { projectId, snapshot, refresh } = useProject();
  return <ApprovalList approvals={snapshot.approvals} projectId={projectId} onRefresh={refresh} />;
}
