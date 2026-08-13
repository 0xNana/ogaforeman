'use client';

import { AppShell } from '@/components/app-shell';
import { ProjectProvider, useProject } from '@/components/project-context';
import { useParams } from 'next/navigation';

export default function ProjectLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  return <ProjectProvider projectId={projectId}><ProjectFrame>{children}</ProjectFrame></ProjectProvider>;
}

function ProjectFrame({ children }: Readonly<{ children: React.ReactNode }>) {
  const { snapshot } = useProject();
  const pendingCount = snapshot.approvals.filter((a) => a.status === 'PENDING').length;
  return <AppShell project={snapshot.project} pendingApprovalCount={pendingCount}>{children}</AppShell>;
}
