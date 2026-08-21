'use client';

import { AlertTriangle, ArrowRight, FileText, Loader2, Upload } from 'lucide-react';
import Link from 'next/link';
import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { clearNewProjectClaim } from '@/components/new-project-wizard';
import {
  api,
  type CreateProjectImportInput,
  type ProjectImportSummary,
} from '@/lib/api';
import {
  clearProjectImportClaim,
  MAX_PROJECT_IMPORT_SOURCE_BYTES,
  persistProjectImportClaim,
  PROJECT_IMPORT_FILE_ACCEPT,
  readProjectImportFile,
  restoreProjectImportClaim,
} from '@/lib/project-import-claim';

function isTextSource(source: CreateProjectImportInput): source is Extract<
  CreateProjectImportInput,
  { source_type: 'text' | 'markdown' }
> {
  return source.source_type === 'text' || source.source_type === 'markdown';
}

export function ProjectImportSetup({ projectId, ownerKey }: Readonly<{ projectId: string; ownerKey: string }>) {
  const router = useRouter();
  const [claim, setClaim] = useState(() => restoreProjectImportClaim(projectId, ownerKey));
  const [latest, setLatest] = useState<ProjectImportSummary | null>(null);
  const [checking, setChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    clearNewProjectClaim();
    persistProjectImportClaim(claim);
  }, [claim]);

  const recoverLatest = useCallback(async () => {
    setChecking(true);
    setRecoveryError('');
    try {
      const current = await api.getLatestProjectImport(projectId);
      if (current && current.status !== 'extraction_failed') {
        clearProjectImportClaim(projectId);
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

  function updateSource(source: CreateProjectImportInput) {
    setClaim((current) => ({
      ownerKey: current.ownerKey,
      projectId: current.projectId,
      idempotencyKey: current.idempotencyKey,
      ...source,
    }));
    setError('');
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const result = await readProjectImportFile(file);
    if (!result.ok) {
      setError(result.error);
      event.target.value = '';
      return;
    }
    updateSource(result.source);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (isTextSource(claim)) {
      const byteSize = new TextEncoder().encode(claim.source_text).byteLength;
      if (!claim.source_text.trim()) {
        setError('Paste your project plan or choose a supported project file.');
        return;
      }
      if (byteSize > MAX_PROJECT_IMPORT_SOURCE_BYTES) {
        setError('That source is larger than the 800 KB import limit.');
        return;
      }
    }
    persistProjectImportClaim(claim);
    setSubmitting(true);
    try {
      const input: CreateProjectImportInput = isTextSource(claim)
        ? {
          source_name: claim.source_name,
          source_text: claim.source_text,
          source_type: claim.source_type,
        }
        : {
          source_name: claim.source_name,
          source_data_base64: claim.source_data_base64,
          source_type: claim.source_type,
        };
      const created = await api.createProjectImport(projectId, input, claim.idempotencyKey);
      clearProjectImportClaim(projectId);
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
    <p className="new-project-lede">Choose a Word, Excel, PDF, CSV, text, or Markdown plan. OG will extract a draft for review; nothing becomes project truth until you confirm it.</p>
    {isRetry ? <div className="import-recovery-alert" role="status"><AlertTriangle size={19} /><div><strong>The previous extraction did not finish.</strong><p>{latest.failure_message ?? 'Your saved source can be retried safely.'}</p></div></div> : null}
    <form className="new-project-form" onSubmit={submit}>
      {error ? <p className="form-alert" role="alert">{error}</p> : null}
      <label className="import-file-field">Choose a project file<input aria-label="Choose a project file" type="file" accept={PROJECT_IMPORT_FILE_ACCEPT} onChange={(event) => void chooseFile(event)} /><span><Upload size={16} /> {claim.source_name === 'pasted-project.md' ? 'No file selected' : claim.source_name}</span></label>
      <div className="import-source-divider"><span>or paste the plan</span></div>
      <label>Plan source<textarea aria-label="Plan source" autoFocus value={isTextSource(claim) ? claim.source_text : ''} onChange={(event) => updateSource({ source_name: 'pasted-project.md', source_text: event.target.value, source_type: 'markdown' })} maxLength={MAX_PROJECT_IMPORT_SOURCE_BYTES} rows={16} placeholder={'# Ridge House plan\n\nTask: Site clearing\nDue: 2026-09-05\n\nMaterials:\n- Cement: 100 bags'} /></label>
      <p className="import-source-note">Google Docs can be exported as Word or PDF. Scanned PDFs need selectable text. BIM, Primavera, and MS Project files are not accepted.</p>
      <div className="new-project-actions"><Link className="btn btn-quiet" href={`/projects/${projectId}`}>Do this later</Link><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? <><Loader2 className="spinner" size={16} /> Extracting plan…</> : <>{isRetry || error ? 'Retry extraction' : 'Extract project plan'} <ArrowRight size={16} /></>}</button></div>
    </form>
  </section>;
}
