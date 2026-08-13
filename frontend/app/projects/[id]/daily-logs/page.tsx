'use client';

import { DailyLogRegister } from '@/components/daily-log-register';
import { useProject } from '@/components/project-context';

export default function DailyLogsPage() {
  const { projectId, snapshot, refresh } = useProject();
  return <DailyLogRegister projectName={snapshot.project.name} projectId={projectId} logs={snapshot.dailyLogs} onRefresh={refresh} />;
}
