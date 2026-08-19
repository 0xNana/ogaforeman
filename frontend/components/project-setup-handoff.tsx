'use client';

import { ArrowRight, FileUp, ListPlus } from 'lucide-react';
import Link from 'next/link';
import { useEffect } from 'react';

import { clearNewProjectClaim } from '@/components/new-project-wizard';

export function ProjectSetupHandoff({ projectId, method }: Readonly<{ projectId: string; method: 'import' | 'empty' }>) {
  useEffect(() => {
    clearNewProjectClaim();
  }, []);

  if (method === 'empty') {
    return <section className="setup-handoff"><span className="setup-handoff-icon"><ListPlus size={24} /></span><span className="eyebrow">Project created</span><h1>Your empty project is ready.</h1><p>Add the first tasks and materials manually. OG will derive setup readiness from the project records you create.</p><div className="setup-handoff-actions"><Link className="btn btn-primary" href={`/projects/${projectId}/tasks`}>Add tasks <ArrowRight size={16} /></Link><Link className="btn btn-quiet" href={`/projects/${projectId}/materials`}>Add materials</Link></div></section>;
  }

  return <section className="setup-handoff"><span className="setup-handoff-icon"><FileUp size={24} /></span><span className="eyebrow">Project created</span><h1>This project is ready for its plan.</h1><p>Your import setup choice is saved in this project-scoped URL. The structured plan entry step will continue here.</p><div className="setup-handoff-actions"><Link className="btn btn-quiet" href={`/projects/${projectId}`}>Go to project overview</Link></div></section>;
}
