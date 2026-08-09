'use client';

import { CommandCenter } from '@/components/command-center';
import { useProject } from '@/components/project-context';

export default function ProjectDashboard() {
  return <CommandCenter snapshot={useProject().snapshot} />;
}
