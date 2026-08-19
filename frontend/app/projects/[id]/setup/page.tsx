'use client';

import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';

import { ProjectImportSetup } from '@/components/project-import-setup';
import { ProjectSetupHandoff } from '@/components/project-setup-handoff';
import { useAuth } from '@/src/lib/auth';

export default function ProjectSetupPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const method = searchParams.get('method') === 'empty' ? 'empty' : 'import';
  const signInHref = `/sign-in?next=${encodeURIComponent(`/projects/${id}/setup?method=${method}`)}`;

  if (auth.state === 'loading') {
    return (
      <div className="new-project-page">
        <div className="container new-project-shell">
          <div className="loading-stack" aria-busy="true">
            <div className="loading-block loading-card" />
          </div>
        </div>
      </div>
    );
  }

  if (auth.state !== 'authenticated') {
    return (
      <div className="new-project-page">
        <div className="empty-state">
          <h1>Sign in to continue project setup.</h1>
          <Link className="btn btn-primary" href={signInHref}>
            Sign in <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="new-project-page">
      <div className="container new-project-shell">
        {method === 'empty'
          ? <ProjectSetupHandoff projectId={id} method="empty" />
          : <ProjectImportSetup projectId={id} ownerKey={auth.user?.uid ?? 'authenticated-user'} />}
      </div>
    </div>
  );
}
