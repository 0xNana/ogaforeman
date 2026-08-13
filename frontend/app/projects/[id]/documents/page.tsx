'use client';

import { DocumentRegister } from '@/components/document-register';
import { useProject } from '@/components/project-context';

export default function DocumentsPage() {
  const { snapshot } = useProject();
  return <DocumentRegister documents={snapshot.documents} />;
}
