import type { CreateProjectImportInput, ProjectImportSourceType } from '@/lib/api';

export const MAX_PROJECT_IMPORT_SOURCE_BYTES = 800_000;
export const MAX_PROJECT_IMPORT_FILE_BYTES = 3_000_000;
export const PROJECT_IMPORT_FILE_ACCEPT = [
  '.txt',
  '.md',
  '.docx',
  '.pdf',
  '.xlsx',
  '.xls',
  '.csv',
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
].join(',');
export const PROJECT_IMPORT_FILE_ERROR = 'Use a Word, Excel, PDF, CSV, text, or Markdown file. BIM, Primavera, and MS Project files are not supported.';
export const PROJECT_IMPORT_SIZE_ERROR = 'That file is larger than the 3 MB import limit.';
export const PROJECT_IMPORT_TEXT_SIZE_ERROR = 'That source is larger than the 800 KB import limit.';
export const PROJECT_IMPORT_READ_ERROR = 'OG could not read that project file. Choose it again or paste the plan below.';

const CLAIM_STORAGE_PREFIX = 'oga:project-import:create-claim';
const volatileClaims = new Map<string, ProjectImportClaim>();

export type ProjectImportClaim = CreateProjectImportInput & {
  autoStart: boolean;
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
  return value === 'text'
    || value === 'markdown'
    || value === 'file'
    || value === 'spreadsheet';
}

function hasValidPayload(value: Partial<ProjectImportClaim>): boolean {
  if (value.source_type === 'text' || value.source_type === 'markdown') {
    return typeof value.source_text === 'string';
  }
  if (value.source_type === 'file' || value.source_type === 'spreadsheet') {
    return typeof value.source_data_base64 === 'string';
  }
  return false;
}

function freshClaim(projectId: string, ownerKey: string): ProjectImportClaim {
  return {
    autoStart: false,
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
      || !isSourceType(value.source_type)
      || !hasValidPayload(value)
    ) return freshClaim(projectId, ownerKey);
    return {
      ...value,
      autoStart: value.autoStart === true,
    } as ProjectImportClaim;
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
  persistProjectImportClaim({
    autoStart: true,
    projectId,
    ownerKey,
    idempotencyKey,
    ...source,
  });
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
  const sourceTypeByExtension: Record<string, ProjectImportSourceType> = {
    '.txt': 'text',
    '.md': 'markdown',
    '.docx': 'file',
    '.pdf': 'file',
    '.xlsx': 'spreadsheet',
    '.xls': 'spreadsheet',
    '.csv': 'spreadsheet',
  };
  const sourceType = sourceTypeByExtension[extension];
  if (!sourceType) return { ok: false, error: PROJECT_IMPORT_FILE_ERROR };
  const sizeLimit = sourceType === 'text' || sourceType === 'markdown'
    ? MAX_PROJECT_IMPORT_SOURCE_BYTES
    : MAX_PROJECT_IMPORT_FILE_BYTES;
  if (file.size > sizeLimit) {
    return {
      ok: false,
      error: sourceType === 'text' || sourceType === 'markdown'
        ? PROJECT_IMPORT_TEXT_SIZE_ERROR
        : PROJECT_IMPORT_SIZE_ERROR,
    };
  }

  try {
    if (sourceType === 'text' || sourceType === 'markdown') {
      const source_text = await file.text();
      if (new TextEncoder().encode(source_text).byteLength > MAX_PROJECT_IMPORT_SOURCE_BYTES) {
        return { ok: false, error: PROJECT_IMPORT_TEXT_SIZE_ERROR };
      }
      return {
        ok: true,
        source: { source_name: file.name, source_text, source_type: sourceType },
      };
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    return {
      ok: true,
      source: {
        source_name: file.name,
        source_data_base64: bytesToBase64(bytes),
        source_type: sourceType,
      },
    };
  } catch {
    return { ok: false, error: PROJECT_IMPORT_READ_ERROR };
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 32_768;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}
