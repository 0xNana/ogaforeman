'use client';

import { ProjectImportReview } from '@/components/project-import-review';
import { useParams, useRouter } from 'next/navigation';

export default function ProjectImportReviewPage() {
  const params = useParams<{ id: string; importId: string }>();
  const router = useRouter();
  return <ProjectImportReview projectId={params.id} importId={params.importId} onFinished={() => router.replace(`/projects/${params.id}`)} />;
}
