import { MessageSquareWarning } from 'lucide-react';
import { ModulePlaceholder } from '@/components/module-placeholder';

export default function IssuesPage() {
  return <ModulePlaceholder title="Issues" description="The project issue log for blockers, quality, safety and coordination." emptyTitle="No issue register available." emptyDescription="Project issues will appear here when the issue projection is available. Existing task blockers remain visible in Tasks." icon={MessageSquareWarning} />;
}
