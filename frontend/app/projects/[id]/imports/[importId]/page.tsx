'use client';

import { ProjectImportReview } from '@/components/project-import-review';
import { useProject } from '@/components/project-context';
import { useParams, useRouter } from 'next/navigation';

export default function ProjectImportReviewPage() {
  const params = useParams<{ id: string; importId: string }>();
  const router = useRouter();
  const project = useProject();
  return (
    <ProjectImportReview
      projectId={params.id}
      importId={params.importId}
      onFinished={async (status) => {
        if (status === 'imported') await project.refresh();
        router.replace(
          status === 'imported'
            ? `/projects/${params.id}`
            : `/projects/${params.id}/setup?method=import`,
        );
      }}
    />
  );
}
