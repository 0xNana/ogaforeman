'use client';

import { ApiRequestError, api, type ProjectSnapshot } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/src/lib/auth';

type ProjectContextValue = {
  projectId: string;
  snapshot: ProjectSnapshot;
  refresh: () => Promise<void>;
};

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ projectId, children }: Readonly<{ projectId: string; children: React.ReactNode }>) {
  const auth = useAuth();
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setSnapshot(await api.getProjectSnapshot(projectId));
    } catch (cause) {
      const nextError = cause instanceof Error ? cause : new Error('Project unavailable.');
      setError(nextError);
      if (cause instanceof ApiRequestError && cause.status === 401) router.replace(`/sign-in?next=/projects/${projectId}`);
    }
  }, [projectId, router]);

  useEffect(() => {
    if (auth.state === 'authenticated') queueMicrotask(() => void refresh());
    if (auth.state === 'signed_out') queueMicrotask(() => router.replace(`/sign-in?next=/projects/${projectId}`));
  }, [auth.state, projectId, refresh, router]);

  const value = useMemo(() => snapshot ? { projectId, snapshot, refresh } : null, [projectId, refresh, snapshot]);

  if (auth.state === 'loading') return <div className="loading-stack" aria-busy="true" aria-label="Checking your session"><p className="loading-label">Checking your session…</p><div className="loading-block loading-heading" /></div>;
  if (auth.state === 'unavailable') return <ProjectAuthError title="Sign-in unavailable" message={auth.error?.message ?? 'Sign-in is not configured for this environment yet.'} />;
  if (error && !snapshot) return <ProjectAuthError title="We couldn't load this project." message="Check your connection or confirm that you still have project access." onRetry={() => void refresh()} />;
  if (!value) return <div className="loading-stack" aria-busy="true" aria-label="Loading project"><p className="loading-label">Loading project…</p><div className="loading-block loading-heading" /><div className="loading-block loading-card" /></div>;

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) throw new Error('useProject must be used inside ProjectProvider');
  return context;
}

function ProjectAuthError({ title, message, onRetry }: Readonly<{ title: string; message: string; onRetry?: () => void }>) {
  return <div className="empty-state" role="alert"><span className="empty-state-icon">!</span><h2>{title}</h2><p>{message}</p>{onRetry ? <button className="btn btn-primary btn-small" type="button" onClick={onRetry}>Try again</button> : null}</div>;
}
