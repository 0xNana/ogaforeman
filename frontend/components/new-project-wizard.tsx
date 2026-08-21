'use client';

import { ArrowLeft, ArrowRight, Upload } from 'lucide-react';
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

type WizardStep = 'method' | 'details';

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
    importIdempotencyKey: `project-import:${crypto.randomUUID()}`,
    importSource: null,
    step: 'method',
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

function projectNameFromSource(sourceName: string): string {
  const withoutExtension = sourceName.replace(/\.[^.]+$/, '');
  const normalized = withoutExtension.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  const name = normalized || 'Imported project';
  return `${name.charAt(0).toUpperCase()}${name.slice(1)}`.slice(0, 200);
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
    const importSource = draft.importSource;
    let input: CreateProjectInput;
    if (draft.step === 'details') {
      if (draft.startDate && draft.targetEndDate && draft.targetEndDate < draft.startDate) {
        setError('Target end date cannot be before the start date.');
        return;
      }
      input = {
        name: draft.name.trim(),
        location: draft.location.trim(),
        description: draft.description.trim() || null,
        timezone: draft.timezone,
        start_date: draft.startDate || null,
        target_end_date: draft.targetEndDate || null,
        status: draft.status,
      };
    } else {
      if (!importSource) {
        setError('Choose a supported project file to continue.');
        return;
      }
      input = {
        name: projectNameFromSource(importSource.source_name),
        location: 'Not specified',
        description: null,
        timezone: draft.timezone,
        start_date: null,
        target_end_date: null,
        status: 'planning',
      };
    }

    setSubmitting(true);
    setHasSubmitted(true);
    try {
      const project = await api.createProject(input, draft.idempotencyKey);
      if (draft.step === 'method' && importSource) {
        stageProjectImportClaim(
          project.id,
          ownerKey,
          importSource,
          draft.importIdempotencyKey,
        );
      }
      const setupPath = `/projects/${project.id}/setup?method=${draft.step === 'method' ? 'import' : 'empty'}`;
      router.replace(setupPath);
    } catch {
      setError('We could not create that project. Your setup is saved here; check your connection and try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="new-project-card" aria-labelledby="new-project-title">
    {draft.step === 'method' ? <>
      <span className="eyebrow">New project</span>
      <h1 id="new-project-title">Tell OG about the project.</h1>
      <p className="new-project-lede">Upload the project file you already use. OG will pull out the project details, schedule, tasks, and materials for you to review.</p>
      <form className="new-project-form" onSubmit={submit} key="import-project-file">
        {error ? <p className="form-alert" role="alert">{error}</p> : null}
        <div className="setup-import-source setup-import-primary">
          <label className="import-file-field">Choose a project file<input aria-label="Choose a project file" type="file" accept={PROJECT_IMPORT_FILE_ACCEPT} onChange={(event) => void chooseImportFile(event)} /><span><Upload size={18} /> {draft.importSource?.source_name ?? 'Choose a Word, Excel, PDF, CSV, text, or Markdown file'}</span></label>
          <p>Word, Excel, PDF, and CSV up to 3 MB; text and Markdown up to 800 KB. Export Google Docs as Word or PDF first.</p>
        </div>
        <div className="new-project-actions"><Link className="btn btn-quiet" href="/projects" onClick={clearNewProjectClaim}><ArrowLeft size={16} /> Cancel</Link><button className="btn btn-primary" type="submit" disabled={submitting || !draft.importSource}>{submitting ? 'Creating project…' : hasSubmitted ? 'Try this file again' : 'Continue with this file'} {!submitting ? <ArrowRight size={16} /> : null}</button></div>
        <div className="import-source-divider"><span>or</span></div>
        <button className="btn btn-quiet manual-project-entry" type="button" onClick={() => { update('step', 'details'); setError(''); }}>Enter project details manually</button>
      </form>
    </> : <>
      <span className="eyebrow">Manual setup</span>
      <h1 id="new-project-title">Add the project details.</h1>
      <p className="new-project-lede">Use this path when you do not have a project file to import.</p>
      <form className="new-project-form" onSubmit={submit} key="manual-project-details">
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
        <div className="new-project-actions"><button className="btn btn-quiet" type="button" onClick={() => { update('step', 'method'); setError(''); }} disabled={submitting}><ArrowLeft size={16} /> Back to import</button><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? 'Creating project…' : hasSubmitted ? 'Try creating empty project again' : 'Create empty project'} {!submitting ? <ArrowRight size={16} /> : null}</button></div>
      </form>
    </>}
  </section>;
}
