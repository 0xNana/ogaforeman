'use client';

import { PhotoRegister } from '@/components/photo-register';
import { api } from '@/lib/api';
import { useProject } from '@/components/project-context';

export default function PhotosPage() {
  const { projectId, snapshot } = useProject();
  return <PhotoRegister photos={snapshot.photos} tasks={snapshot.tasks} issues={snapshot.issues} dailyLogs={snapshot.dailyLogs} loadUrl={(attachmentId) => api.getAttachmentReadUrl(projectId, attachmentId)} />;
}
