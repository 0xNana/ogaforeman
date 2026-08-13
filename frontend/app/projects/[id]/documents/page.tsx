import { FolderOpen } from 'lucide-react';
import { ModulePlaceholder } from '@/components/module-placeholder';

export default function DocumentsPage() {
  return <ModulePlaceholder title="Documents" description="Project files, revisions and linked records." emptyTitle="No documents available." emptyDescription="Uploaded project documents will appear here when document metadata is available." icon={FolderOpen} />;
}
