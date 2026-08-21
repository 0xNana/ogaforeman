import type { CreateProjectImportInput, ProjectImportSourceType } from '@/lib/api';

export const MAX_PROJECT_IMPORT_SOURCE_BYTES = 800_000;
export const PROJECT_IMPORT_FILE_ACCEPT = '.txt,.md,text/plain,text/markdown';
export const PROJECT_IMPORT_FILE_ERROR = 'Use a .txt or .md file. PDF, spreadsheet, and project-schedule files are not supported in V1.';
export const PROJECT_IMPORT_SIZE_ERROR = 'That source is larger than the 800 KB import limit.';
export const PROJECT_IMPORT_READ_ERROR = 'OG could not read that text file. Choose it again or paste the plan below.';

const CLAIM_STORAGE_PREFIX = 'oga:project-import:create-claim';
const volatileClaims = new Map<string, ProjectImportClaim>();

export type ProjectImportClaim = CreateProjectImportInput & {
  ownerKey: string;
  projectId: string;
  idempotencyKey: string;
};

export type ProjectImportFileResult =
  | { ok: true; source: CreateProjectImportInput }
  | { ok: false; error: string };

function storageKey(projectId: string): string {
  return `${CLAIM_STORAGE_PREFIX}:${projectId}`;
}

function isSourceType(value: unknown): value is ProjectImportSourceType {
  return value === 'text' || value === 'markdown';
}

function freshClaim(projectId: string, ownerKey: string): ProjectImportClaim {
  return {
    ownerKey,
    projectId,
    idempotencyKey: `project-import:${crypto.randomUUID()}`,
    source_name: 'pasted-project.md',
    source_text: '',
    source_type: 'markdown',
  };
}

export function restoreProjectImportClaim(projectId: string, ownerKey: string): ProjectImportClaim {
  if (typeof window === 'undefined') return freshClaim(projectId, ownerKey);
  try {
    const raw = window.sessionStorage.getItem(storageKey(projectId));
    const value = raw
      ? JSON.parse(raw) as Partial<ProjectImportClaim>
      : volatileClaims.get(projectId);
    if (!value) return freshClaim(projectId, ownerKey);
    if (
      value.ownerKey !== ownerKey
      || value.projectId !== projectId
      || typeof value.idempotencyKey !== 'string'
      || typeof value.source_name !== 'string'
      || typeof value.source_text !== 'string'
      || !isSourceType(value.source_type)
    ) return freshClaim(projectId, ownerKey);
    return value as ProjectImportClaim;
  } catch {
    return freshClaim(projectId, ownerKey);
  }
}

export function persistProjectImportClaim(claim: ProjectImportClaim): void {
  volatileClaims.set(claim.projectId, claim);
  try {
    window.sessionStorage.setItem(storageKey(claim.projectId), JSON.stringify(claim));
  } catch {
    // The in-memory claim still protects retries during this page lifetime.
  }
}

export function stageProjectImportClaim(
  projectId: string,
  ownerKey: string,
  source: CreateProjectImportInput,
  idempotencyKey: string,
): void {
  persistProjectImportClaim({ projectId, ownerKey, idempotencyKey, ...source });
}

export function clearProjectImportClaim(projectId: string): void {
  volatileClaims.delete(projectId);
  try {
    window.sessionStorage.removeItem(storageKey(projectId));
  } catch {
    // No persisted browser claim remains to clear.
  }
}

export async function readProjectImportFile(file: File): Promise<ProjectImportFileResult> {
  const extension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
  if (extension !== '.txt' && extension !== '.md') return { ok: false, error: PROJECT_IMPORT_FILE_ERROR };
  if (file.size > MAX_PROJECT_IMPORT_SOURCE_BYTES) return { ok: false, error: PROJECT_IMPORT_SIZE_ERROR };

  try {
    const source_text = await file.text();
    if (new TextEncoder().encode(source_text).byteLength > MAX_PROJECT_IMPORT_SOURCE_BYTES) {
      return { ok: false, error: PROJECT_IMPORT_SIZE_ERROR };
    }
    return {
      ok: true,
      source: {
        source_name: file.name,
        source_text,
        source_type: extension === '.md' ? 'markdown' : 'text',
      },
    };
  } catch {
    return { ok: false, error: PROJECT_IMPORT_READ_ERROR };
  }
}
