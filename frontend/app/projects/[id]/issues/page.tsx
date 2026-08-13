'use client';

import { IssueRegister } from '@/components/issue-register';
import { useProject } from '@/components/project-context';

export default function IssuesPage() {
  const { snapshot } = useProject();
  return <IssueRegister issues={snapshot.issues} tasks={snapshot.tasks} />;
}
