'use client';

import { ArrowRight } from 'lucide-react';
import Link from 'next/link';

import { NewProjectWizard } from '@/components/new-project-wizard';
import { useAuth } from '@/src/lib/auth';

export default function NewProjectPage() {
  const auth = useAuth();

  if (auth.state === 'loading') return <main className="new-project-page"><div className="container"><div className="loading-stack" aria-busy="true"><div className="loading-block loading-card" /></div></div></main>;
  if (auth.state !== 'authenticated') return <main className="new-project-page"><div className="empty-state"><h1>Sign in to create a project.</h1><Link className="btn btn-primary" href="/sign-in?next=/projects/new">Sign in <ArrowRight size={16} /></Link></div></main>;

  return <main className="new-project-page"><div className="container new-project-shell"><NewProjectWizard ownerKey={auth.user?.uid ?? 'authenticated-user'} /></div></main>;
}
