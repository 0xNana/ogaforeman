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
  return <AppShell project={snapshot.project}>{children}</AppShell>;
}
