'use client';

import { ArrowLeft, ArrowRight, FileUp, ListPlus, Upload } from 'lucide-react';
import Link from 'next/link';
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import {
  api,
  type CreateProjectImportInput,
  type CreateProjectInput,
  type CreateProjectStatus,
} from '@/lib/api';
import {
  PROJECT_IMPORT_FILE_ACCEPT,
  readProjectImportFile,
  stageProjectImportClaim,
} from '@/lib/project-import-claim';

export const NEW_PROJECT_CLAIM_STORAGE_KEY = 'oga:new-project:create-claim';

type SetupMethod = 'import' | 'empty';
type WizardStep = 'details' | 'method';

type ProjectDraft = {
  ownerKey: string;
  idempotencyKey: string;
  name: string;
  location: string;
  description: string;
  timezone: string;
  startDate: string;
  targetEndDate: string;
  status: CreateProjectStatus;
  setupMethod: SetupMethod;
  importIdempotencyKey: string;
  importSource: CreateProjectImportInput | null;
  step: WizardStep;
};

const FALLBACK_TIMEZONES = [
  'Africa/Accra',
  'Africa/Lagos',
  'Africa/Nairobi',
  'Africa/Johannesburg',
  'Europe/London',
  'UTC',
];

function detectedTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Africa/Accra';
}

function freshDraft(ownerKey: string): ProjectDraft {
  return {
    ownerKey,
    idempotencyKey: `project:${crypto.randomUUID()}`,
    name: '',
    location: '',
    description: '',
    timezone: detectedTimezone(),
    startDate: '',
    targetEndDate: '',
    status: 'planning',
    setupMethod: 'import',
    importIdempotencyKey: `project-import:${crypto.randomUUID()}`,
    importSource: null,
    step: 'details',
  };
}

function restoreDraft(ownerKey: string): ProjectDraft {
  if (typeof window === 'undefined') return freshDraft(ownerKey);
  try {
    const stored = window.sessionStorage.getItem(NEW_PROJECT_CLAIM_STORAGE_KEY);
    if (!stored) return freshDraft(ownerKey);
    const parsed = JSON.parse(stored) as Partial<ProjectDraft>;
    return parsed.ownerKey === ownerKey
      ? { ...freshDraft(ownerKey), ...parsed }
      : freshDraft(ownerKey);
  } catch {
    return freshDraft(ownerKey);
  }
}

function persistDraft(draft: ProjectDraft): void {
  try {
    window.sessionStorage.setItem(NEW_PROJECT_CLAIM_STORAGE_KEY, JSON.stringify(draft));
  } catch {
    // A stable in-memory claim still protects retries when storage is unavailable.
  }
}

export function clearNewProjectClaim(): void {
  try {
    window.sessionStorage.removeItem(NEW_PROJECT_CLAIM_STORAGE_KEY);
  } catch {
    // There is no persisted browser claim to clear.
  }
}

export function NewProjectWizard({ ownerKey = 'test-user' }: Readonly<{ ownerKey?: string }>) {
  const router = useRouter();
  const [draft, setDraft] = useState<ProjectDraft>(() => restoreDraft(ownerKey));
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const timezones = useMemo(() => {
    const intl = Intl as typeof Intl & { supportedValuesOf?: (key: 'timeZone') => string[] };
    const supported = intl.supportedValuesOf?.('timeZone') ?? FALLBACK_TIMEZONES;
    return Array.from(new Set([draft.timezone, ...supported])).sort();
  }, [draft.timezone]);

  useEffect(() => {
    persistDraft(draft);
  }, [draft]);

  function update<K extends keyof ProjectDraft>(field: K, value: ProjectDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function chooseImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const result = await readProjectImportFile(file);
    if (!result.ok) {
      setError(result.error);
      event.target.value = '';
      return;
    }
    update('importSource', result.source);
    setError('');
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (draft.step === 'details') {
      if (draft.startDate && draft.targetEndDate && draft.targetEndDate < draft.startDate) {
        setError('Target end date cannot be before the start date.');
        return;
      }
      update('step', 'method');
      return;
    }

    setSubmitting(true);
    setHasSubmitted(true);
    const input: CreateProjectInput = {
      name: draft.name.trim(),
      location: draft.location.trim(),
      description: draft.description.trim() || null,
      timezone: draft.timezone,
      start_date: draft.startDate || null,
      target_end_date: draft.targetEndDate || null,
      status: draft.status,
    };
    try {
      const project = await api.createProject(input, draft.idempotencyKey);
      if (draft.setupMethod === 'import' && draft.importSource) {
        stageProjectImportClaim(
          project.id,
          ownerKey,
          draft.importSource,
          draft.importIdempotencyKey,
        );
      }
      const setupPath = `/projects/${project.id}/setup?method=${draft.setupMethod}`;
      router.replace(setupPath);
    } catch {
      setError('We could not create that project. Your details are saved here; check your connection and try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="new-project-card" aria-labelledby="new-project-title">
    <div className="new-project-progress" aria-label="Project setup progress">
      <span className={draft.step === 'details' ? 'active' : 'complete'}><b>1</b> Project details</span>
      <span className={draft.step === 'method' ? 'active' : ''}><b>2</b> Setup method</span>
    </div>
    {draft.step === 'details' ? <>
      <span className="eyebrow">New project</span>
      <h1 id="new-project-title">Tell OG about the site.</h1>
      <p className="new-project-lede">Create the project first, then bring in an existing plan or build the work manually.</p>
      <form className="new-project-form" onSubmit={submit}>
        {error ? <p className="form-alert" role="alert">{error}</p> : null}
        <div className="new-project-grid">
          <label>Project name<input autoFocus value={draft.name} onChange={(event) => update('name', event.target.value)} required maxLength={200} placeholder="Ridge House" /></label>
          <label>Location<input value={draft.location} onChange={(event) => update('location', event.target.value)} required maxLength={500} placeholder="East Legon, Accra" /></label>
          <label className="field-span">Description <span aria-hidden="true">Optional</span><textarea aria-label="Description" value={draft.description} onChange={(event) => update('description', event.target.value)} maxLength={5000} rows={4} placeholder="A short description of the site and scope" /></label>
          <label>Start date <span aria-hidden="true">Optional</span><input aria-label="Start date" type="date" value={draft.startDate} onChange={(event) => update('startDate', event.target.value)} /></label>
          <label>Target end date <span aria-hidden="true">Optional</span><input aria-label="Target end date" type="date" value={draft.targetEndDate} onChange={(event) => update('targetEndDate', event.target.value)} /></label>
          <label>Timezone<select value={draft.timezone} onChange={(event) => update('timezone', event.target.value)} required>{timezones.map((timezone) => <option key={timezone} value={timezone}>{timezone.replaceAll('_', ' ')}</option>)}</select></label>
          <label>Project status<select value={draft.status} onChange={(event) => update('status', event.target.value as CreateProjectStatus)}><option value="planning">Planning</option><option value="active">Active</option><option value="paused">Paused</option></select></label>
        </div>
        <div className="new-project-actions"><Link className="btn btn-quiet" href="/projects" onClick={clearNewProjectClaim}><ArrowLeft size={16} /> Cancel</Link><button className="btn btn-primary" type="submit">Continue to setup <ArrowRight size={16} /></button></div>
      </form>
    </> : <>
      <span className="eyebrow">Setup method</span>
      <h1 id="new-project-title">How do you want to set up the work?</h1>
      <p className="new-project-lede">You can add the project plan now or begin with an empty workspace.</p>
      <form className="new-project-form" onSubmit={submit}>
        {error ? <p className="form-alert" role="alert">{error}</p> : null}
        <fieldset className="setup-methods"><legend className="sr-only">Choose a setup method</legend>
          <label className={draft.setupMethod === 'import' ? 'setup-method selected' : 'setup-method'}><input type="radio" name="setup-method" value="import" checked={draft.setupMethod === 'import'} onChange={() => update('setupMethod', 'import')} /><span className="setup-method-icon"><FileUp size={22} /></span><span><strong>Import an existing plan</strong><small>Recommended · Choose a Word, Excel, PDF, CSV, text, or Markdown file.</small></span></label>
          <label className={draft.setupMethod === 'empty' ? 'setup-method selected' : 'setup-method'}><input type="radio" name="setup-method" value="empty" checked={draft.setupMethod === 'empty'} onChange={() => update('setupMethod', 'empty')} /><span className="setup-method-icon"><ListPlus size={22} /></span><span><strong>Start empty</strong><small>Add tasks and materials manually after the project is created.</small></span></label>
        </fieldset>
        {draft.setupMethod === 'import' ? <div className="setup-import-source">
          <label className="import-file-field">Choose a project file<input aria-label="Choose a project file" type="file" accept={PROJECT_IMPORT_FILE_ACCEPT} onChange={(event) => void chooseImportFile(event)} /><span><Upload size={16} /> {draft.importSource?.source_name ?? 'Select project file'}</span></label>
          <p>Word, Excel, PDF, and CSV up to 3 MB; text and Markdown up to 800 KB.</p>
        </div> : null}
        <div className="project-draft-summary"><span>Creating</span><strong>{draft.name.trim()}</strong><small>{draft.location.trim()}</small></div>
        <div className="new-project-actions"><button className="btn btn-quiet" type="button" onClick={() => update('step', 'details')} disabled={submitting}><ArrowLeft size={16} /> Back</button><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? 'Creating project…' : hasSubmitted ? 'Try creating again' : 'Create project'} {!submitting ? <ArrowRight size={16} /> : null}</button></div>
      </form>
    </>}
  </section>;
}
