import { CalendarDays } from 'lucide-react';
import { ModulePlaceholder } from '@/components/module-placeholder';

export default function SchedulePage() {
  return <ModulePlaceholder title="Schedule" description="Project activities, dates and downstream impact." emptyTitle="No schedule activities available." emptyDescription="Activities will appear here when dated task and dependency records are available for this project." icon={CalendarDays} />;
}
