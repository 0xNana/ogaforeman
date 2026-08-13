'use client';

import { useProject } from '@/components/project-context';
import { ScheduleRegister } from '@/components/schedule-register';

export default function SchedulePage() {
  const { snapshot } = useProject();
  return <ScheduleRegister tasks={snapshot.tasks} />;
}
