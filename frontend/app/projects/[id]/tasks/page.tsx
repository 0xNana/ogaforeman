'use client';

import { useProject } from '@/components/project-context';
import { TaskBoard } from '@/components/task-board';

export default function TasksPage() {
  const { projectId, snapshot, refresh } = useProject();
  return <TaskBoard projectId={projectId} tasks={snapshot.tasks} viewerId={snapshot.viewerId ?? null} onRefresh={refresh} />;
}
