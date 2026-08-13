import { Camera } from 'lucide-react';
import { ModulePlaceholder } from '@/components/module-placeholder';

export default function PhotosPage() {
  return <ModulePlaceholder title="Photos" description="Site photos organized by date and linked project records." emptyTitle="No photo register available." emptyDescription="Photos submitted to OG will appear here when their project metadata and record links are available." icon={Camera} />;
}
