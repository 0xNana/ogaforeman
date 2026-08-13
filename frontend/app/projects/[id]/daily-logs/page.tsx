import { FileClock } from 'lucide-react';
import { ModulePlaceholder } from '@/components/module-placeholder';

export default function DailyLogsPage() {
  return <ModulePlaceholder title="Daily Logs" description="A dated record of site progress, crews, delays and deliveries." emptyTitle="No daily logs available." emptyDescription="Daily logs will appear here when historical report dates are available. The current report remains under Reports." icon={FileClock} />;
}
