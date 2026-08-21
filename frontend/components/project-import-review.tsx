'use client';

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RotateCw,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { PageHeader } from '@/components/page-header';
import { ProjectImportDraftDetails } from '@/components/project-import-draft-details';
import {
  api,
  ApiRequestError,
  type ProjectImportReviewRecord,
  type ProjectImportStatus,
} from '@/lib/api';

type ProjectImportReviewProps = {
  projectId: string;
  importId: string;
  onFinished: (status: 'imported' | 'cancelled') => void | Promise<void>;
};

type Decision = 'confirm' | 'cancel' | 'retry';

const ACTIVE_STATES = new Set<ProjectImportStatus>([
  'uploaded',
  'extracting',
  'draft',
  'validating',
  'confirmed',
  'importing',
]);

const ACTIVE_STATE_COPY: Partial<Record<ProjectImportStatus, { title: string; text: string }>> = {
  uploaded: { title: 'Source uploaded.', text: 'OG is preparing the saved source for extraction.' },
  extracting: { title: 'Extracting project plan.', text: 'OG is turning the saved source into a structured draft.' },
  draft: { title: 'Draft extracted.', text: 'The draft is saved and waiting for deterministic validation.' },
  validating: { title: 'Validating project plan.', text: 'OG is checking references, units, dependencies, and safe write limits.' },
  confirmed: { title: 'Initialization confirmed.', text: 'Your decision is saved and the canonical import is ready to continue.' },
  importing: { title: 'Initializing project.', text: 'OG is atomically creating the reviewed project records.' },
};

function decisionStorageKey(projectId: string, importId: string, action: Decision): string {
  return `oga:project-import:decision-claim:${projectId}:${importId}:${action}`;
}

function restoreDecisionKey(projectId: string, importId: string, action: Decision): string {
  const key = decisionStorageKey(projectId, importId, action);
  try {
    const stored = window.sessionStorage.getItem(key);
    if (stored) return stored;
    const created = `project-import-${action}:${crypto.randomUUID()}`;
    window.sessionStorage.setItem(key, created);
    return created;
  } catch {
    return `project-import-${action}:${crypto.randomUUID()}`;
  }
}

function restoreRetryKey(projectId: string, importId: string, version: number): string {
  const key = `oga:project-import:retry-claim:${projectId}:${importId}:${version}`;
  try {
    const stored = window.sessionStorage.getItem(key);
    if (stored) return stored;
    const created = `project-import-retry:${crypto.randomUUID()}`;
    window.sessionStorage.setItem(key, created);
    return created;
  } catch {
    return `project-import-retry:${crypto.randomUUID()}`;
  }
}

export function ProjectImportReview({ projectId, importId, onFinished }: Readonly<ProjectImportReviewProps>) {
  const [review, setReview] = useState<ProjectImportReviewRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const decisionInFlight = useRef(false);
  const keys = useRef({
    confirm: restoreDecisionKey(projectId, importId, 'confirm'),
    cancel: restoreDecisionKey(projectId, importId, 'cancel'),
  });

  const loadReview = useCallback(async () => {
    setError(null);
    try {
      const current = await api.getProjectImport(projectId, importId);
      setReview(current);
      return current;
    } catch (cause) {
      setError(errorMessage(cause, 'The import review could not be loaded.'));
      return null;
    }
  }, [importId, projectId]);

  useEffect(() => {
    queueMicrotask(() => void loadReview());
  }, [loadReview]);

  useEffect(() => {
    if (!review || !ACTIVE_STATES.has(review.status)) return;
    const timer = window.setTimeout(() => void loadReview(), 2_500);
    return () => window.clearTimeout(timer);
  }, [loadReview, review]);

  if (error && !review) {
    return (
      <ImportStatePage>
        <ReviewState
          alert
          icon={<AlertTriangle />}
          title="We couldn’t load this import."
          text={error}
          actions={<button className="btn btn-primary btn-small" type="button" onClick={() => void loadReview()}>Try again</button>}
        />
      </ImportStatePage>
    );
  }
  if (!review) return <ImportLoading />;

  const activeCopy = ACTIVE_STATE_COPY[review.status];
  if (activeCopy) {
    return (
      <ImportStatePage>
        <ReviewState
          busy
          icon={<Loader2 className="spinner" />}
          title={activeCopy.title}
          text={activeCopy.text}
          actions={<button className="btn btn-quiet" type="button" onClick={() => void loadReview()}><RotateCw size={16} /> Check status</button>}
        />
        <StateError message={error} />
      </ImportStatePage>
    );
  }

  const hasConflicts = review.conflicts.length > 0;
  const canCancel = ['needs_review', 'validation_failed', 'extraction_failed', 'import_failed'].includes(review.status);
  const canConfirm = ['needs_review', 'import_failed'].includes(review.status) && !hasConflicts;
  const canRetryExtraction = review.retryable && ['validation_failed', 'extraction_failed'].includes(review.status);
  const expectedVersion = review.version;

  async function recoverCurrentVersion() {
    try {
      setReview(await api.getProjectImport(projectId, importId));
      setError('This import changed while you were deciding. The latest version is loaded; review it before trying again.');
    } catch (cause) {
      setError(errorMessage(cause, 'The latest import version could not be loaded.'));
    }
  }

  async function decide(action: Decision) {
    if (decisionInFlight.current) return;
    if (action === 'retry') return;
    if (action === 'confirm' ? !canConfirm : !canCancel) return;
    decisionInFlight.current = true;
    setDecision(action);
    setError(null);
    try {
      const result = action === 'confirm'
        ? await api.confirmProjectImport(projectId, importId, expectedVersion, keys.current.confirm)
        : await api.cancelProjectImport(projectId, importId, expectedVersion, keys.current.cancel);
      setReview(result);
      if (result.status === 'imported' || result.status === 'cancelled') await onFinished(result.status);
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.code === 'PROJECT_IMPORT_VERSION_CONFLICT') {
        await recoverCurrentVersion();
      } else {
        setError(errorMessage(cause, 'The import decision could not be saved.'));
      }
    } finally {
      decisionInFlight.current = false;
      setDecision(null);
    }
  }

  async function retryExtraction() {
    if (decisionInFlight.current || !canRetryExtraction) return;
    decisionInFlight.current = true;
    setDecision('retry');
    setError(null);
    try {
      setReview(await api.retryProjectImport(
        projectId,
        importId,
        expectedVersion,
        restoreRetryKey(projectId, importId, expectedVersion),
      ));
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.code === 'PROJECT_IMPORT_VERSION_CONFLICT') {
        await recoverCurrentVersion();
      } else {
        setError(errorMessage(cause, 'OG could not retry extraction from the saved source.'));
      }
    } finally {
      decisionInFlight.current = false;
      setDecision(null);
    }
  }

  if (review.status === 'extraction_failed') {
    return (
      <ImportStatePage>
        <ReviewState
          icon={<AlertTriangle />}
          title="Extraction did not finish."
          text={review.failure_message ?? 'OG could not create a review draft from the saved source.'}
          actions={(
            <>
              <button className="btn btn-quiet" type="button" disabled={decision !== null} onClick={() => void decide('cancel')}>Cancel Import</button>
              <Link className="btn btn-quiet" href={`/projects/${projectId}/setup?method=import`}>Choose a different file</Link>
              <button className="btn btn-primary" type="button" disabled={decision !== null || !canRetryExtraction} onClick={() => void retryExtraction()}>
                {decision === 'retry' ? <><Loader2 className="spinner" size={16} /> Retrying…</> : <><RotateCw size={16} /> Retry extraction</>}
              </button>
            </>
          )}
        />
        <StateError message={error} />
      </ImportStatePage>
    );
  }

  if (review.status === 'imported' || review.status === 'cancelled') {
    const imported = review.status === 'imported';
    return (
      <ImportStatePage>
        <ReviewState
          icon={imported ? <CheckCircle2 /> : <XCircle />}
          title={imported ? 'Project initialized.' : 'Import cancelled.'}
          text={imported ? 'OG has created the reviewed project records.' : 'No canonical project records were created from this draft.'}
          actions={(
            <Link className="btn btn-primary" href={imported ? `/projects/${projectId}` : `/projects/${projectId}/setup?method=import`}>
              {imported ? 'Open project overview' : 'Return to setup'}
            </Link>
          )}
        />
        <StateError message={error} />
      </ImportStatePage>
    );
  }

  return (
    <div className="import-review-page">
      <PageHeader eyebrow="Project setup" title="Review project initialization" description="Check what OG will create. Nothing becomes project truth until you confirm." />
      <ProjectImportDraftDetails review={review} />

      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="import-review-actions">
        <button className="btn btn-quiet" type="button" disabled={decision !== null || !canCancel} onClick={() => void decide('cancel')}>
          {decision === 'cancel' ? <><Loader2 className="spinner" size={16} /> Cancelling…</> : 'Cancel Import'}
        </button>
        {canRetryExtraction ? (
          <button className="btn btn-primary" type="button" disabled={decision !== null} onClick={() => void retryExtraction()}>
            {decision === 'retry' ? <><Loader2 className="spinner" size={16} /> Retrying…</> : <><RotateCw size={16} /> Retry extraction</>}
          </button>
        ) : null}
        <button className="btn btn-accent" type="button" disabled={decision !== null || !canConfirm} onClick={() => void decide('confirm')}>
          {decision === 'confirm'
            ? <><Loader2 className="spinner" size={16} /> Initializing…</>
            : review.status === 'import_failed' ? 'Retry initialization' : 'Confirm & Initialize'}
        </button>
        {!canConfirm ? <p>Resolve the items above before initializing the project.</p> : null}
      </div>
    </div>
  );
}

function ImportLoading() {
  return <div className="loading-stack" aria-busy="true" aria-label="Loading import review"><p className="loading-label">Loading import review…</p><div className="loading-block loading-heading" /><div className="loading-block loading-card" /></div>;
}

function ImportStatePage({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="import-review-page"><PageHeader eyebrow="Project setup" title="Project initialization" description="This page reflects the latest durable import state." />{children}</div>;
}

function ReviewState({ icon, title, text, actions, busy = false, alert = false }: Readonly<{ icon: React.ReactNode; title: string; text: string; actions?: React.ReactNode; busy?: boolean; alert?: boolean }>) {
  return <section className="import-state" role={alert ? 'alert' : busy ? 'status' : undefined} aria-busy={busy || undefined}><span className="import-state-icon" aria-hidden="true">{icon}</span><div><h2>{title}</h2><p>{text}</p>{actions ? <div className="import-state-actions">{actions}</div> : null}</div></section>;
}

function StateError({ message }: Readonly<{ message: string | null }>) {
  return message ? <p className="form-error" role="alert">{message}</p> : null;
}

function errorMessage(cause: unknown, fallback: string) { return cause instanceof Error ? cause.message : fallback; }
