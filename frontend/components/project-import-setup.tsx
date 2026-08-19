'use client';

import { AlertTriangle, ArrowRight, FileText, Loader2, Upload } from 'lucide-react';
import Link from 'next/link';
import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { clearNewProjectClaim } from '@/components/new-project-wizard';
import {
  api,
  type CreateProjectImportInput,
  type ProjectImportSourceType,
  type ProjectImportSummary,
} from '@/lib/api';

const MAX_SOURCE_BYTES = 800_000;
const CLAIM_STORAGE_PREFIX = 'oga:project-import:create-claim';

type ImportClaim = CreateProjectImportInput & {
  ownerKey: string;
  projectId: string;
  idempotencyKey: string;
};

function storageKey(projectId: string): string {
  return `${CLAIM_STORAGE_PREFIX}:${projectId}`;
}

function freshClaim(projectId: string, ownerKey: string): ImportClaim {
  return {
    ownerKey,
    projectId,
    idempotencyKey: `project-import:${crypto.randomUUID()}`,
    source_name: 'pasted-project.md',
    source_text: '',
    source_type: 'markdown',
  };
}

function restoreClaim(projectId: string, ownerKey: string): ImportClaim {
  if (typeof window === 'undefined') return freshClaim(projectId, ownerKey);
  try {
    const raw = window.sessionStorage.getItem(storageKey(projectId));
    if (!raw) return freshClaim(projectId, ownerKey);
    const value = JSON.parse(raw) as Partial<ImportClaim>;
    const sourceType = value.source_type;
    if (
      value.ownerKey !== ownerKey
      || value.projectId !== projectId
      || typeof value.idempotencyKey !== 'string'
      || typeof value.source_name !== 'string'
      || typeof value.source_text !== 'string'
      || (sourceType !== 'text' && sourceType !== 'markdown')
    ) return freshClaim(projectId, ownerKey);
    return value as ImportClaim;
  } catch {
    return freshClaim(projectId, ownerKey);
  }
}

function persistClaim(claim: ImportClaim): void {
  try {
    window.sessionStorage.setItem(storageKey(claim.projectId), JSON.stringify(claim));
  } catch {
    // The in-memory claim still protects retries during this page lifetime.
  }
}

function clearClaim(projectId: string): void {
  try {
    window.sessionStorage.removeItem(storageKey(projectId));
  } catch {
    // No persisted browser claim remains to clear.
  }
}

export function ProjectImportSetup({ projectId, ownerKey }: Readonly<{ projectId: string; ownerKey: string }>) {
  const router = useRouter();
  const [claim, setClaim] = useState<ImportClaim>(() => restoreClaim(projectId, ownerKey));
  const [latest, setLatest] = useState<ProjectImportSummary | null>(null);
  const [checking, setChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    clearNewProjectClaim();
    persistClaim(claim);
  }, [claim]);

  const recoverLatest = useCallback(async () => {
    setChecking(true);
    setRecoveryError('');
    try {
      const current = await api.getLatestProjectImport(projectId);
      if (current && current.status !== 'extraction_failed') {
        clearClaim(projectId);
        router.replace(`/projects/${projectId}/imports/${current.id}`);
        return;
      }
      setLatest(current);
    } catch {
      setRecoveryError('Your project is ready, but OG could not check its import history. Try that check again before starting another import.');
    } finally {
      setChecking(false);
    }
  }, [projectId, router]);

  useEffect(() => {
    queueMicrotask(() => void recoverLatest());
  }, [recoverLatest]);

  function updateSource(sourceText: string, sourceName = claim.source_name, sourceType = claim.source_type) {
    setClaim((current) => ({
      ...current,
      source_name: sourceName,
      source_text: sourceText,
      source_type: sourceType,
    }));
    setError('');
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const extension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (extension !== '.txt' && extension !== '.md') {
      setError('Use a .txt or .md file. PDF, spreadsheet, and project-schedule files are not supported in V1.');
      event.target.value = '';
      return;
    }
    if (file.size > MAX_SOURCE_BYTES) {
      setError('That source is larger than the 800 KB import limit.');
      event.target.value = '';
      return;
    }
    try {
      const text = await file.text();
      const sourceType: ProjectImportSourceType = extension === '.md' ? 'markdown' : 'text';
      updateSource(text, file.name, sourceType);
    } catch {
      setError('OG could not read that text file. Choose it again or paste the plan below.');
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const byteSize = new TextEncoder().encode(claim.source_text).byteLength;
    if (!claim.source_text.trim()) {
      setError('Paste your project plan or choose a .txt or .md file.');
      return;
    }
    if (byteSize > MAX_SOURCE_BYTES) {
      setError('That source is larger than the 800 KB import limit.');
      return;
    }
    persistClaim(claim);
    setSubmitting(true);
    try {
      const created = await api.createProjectImport(projectId, {
        source_name: claim.source_name,
        source_text: claim.source_text,
        source_type: claim.source_type,
      }, claim.idempotencyKey);
      clearClaim(projectId);
      router.replace(`/projects/${projectId}/imports/${created.id}`);
    } catch {
      setLatest((current) => current ?? null);
      setError('OG couldn’t start extraction. Your source and retry claim are saved in this tab; try again when the service is available.');
    } finally {
      setSubmitting(false);
    }
  }

  if (checking) return <div className="loading-stack" aria-busy="true" aria-label="Checking project imports"><p className="loading-label">Checking for an existing import…</p><div className="loading-block loading-card" /></div>;
  if (recoveryError) return <section className="setup-handoff"><span className="setup-handoff-icon"><AlertTriangle /></span><h1>We couldn’t check project setup.</h1><p role="alert">{recoveryError}</p><div className="setup-handoff-actions"><button className="btn btn-primary" type="button" onClick={() => void recoverLatest()}>Check again</button><Link className="btn btn-quiet" href={`/projects/${projectId}`}>Project overview</Link></div></section>;

  const isRetry = latest?.status === 'extraction_failed';
  return <section className="new-project-card project-import-setup" aria-labelledby="project-import-title">
    <span className="setup-handoff-icon"><FileText size={24} /></span>
    <span className="eyebrow">Project created</span>
    <h1 id="project-import-title">{isRetry ? 'Extraction needs another try.' : 'Add your project plan.'}</h1>
    <p className="new-project-lede">Paste structured text, Markdown, or an OG template. OG will extract a draft for review; nothing becomes project truth until you confirm it.</p>
    {isRetry ? <div className="import-recovery-alert" role="status"><AlertTriangle size={19} /><div><strong>The previous extraction did not finish.</strong><p>{latest.failure_message ?? 'Your saved source can be retried safely.'}</p></div></div> : null}
    <form className="new-project-form" onSubmit={submit}>
      {error ? <p className="form-alert" role="alert">{error}</p> : null}
      <label className="import-file-field">Choose a .txt or .md file<input aria-label="Choose a .txt or .md file" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => void chooseFile(event)} /><span><Upload size={16} /> {claim.source_name === 'pasted-project.md' ? 'No file selected' : claim.source_name}</span></label>
      <div className="import-source-divider"><span>or paste the plan</span></div>
      <label>Plan source<textarea aria-label="Plan source" autoFocus value={claim.source_text} onChange={(event) => updateSource(event.target.value, 'pasted-project.md', 'markdown')} maxLength={MAX_SOURCE_BYTES} rows={16} placeholder={'# Ridge House plan\n\nTask: Site clearing\nDue: 2026-09-05\n\nMaterials:\n- Cement: 100 bags'} /></label>
      <p className="import-source-note">Only text is read from your browser. PDFs, spreadsheets, Primavera, MS Project, and BIM files are not accepted in V1.</p>
      <div className="new-project-actions"><Link className="btn btn-quiet" href={`/projects/${projectId}`}>Do this later</Link><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? <><Loader2 className="spinner" size={16} /> Extracting plan…</> : <>{isRetry || error ? 'Retry extraction' : 'Extract project plan'} <ArrowRight size={16} /></>}</button></div>
    </form>
  </section>;
}
