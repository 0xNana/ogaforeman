import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, setApiTokenProvider, type ProjectImportSummary } from './api';

const failedImport: ProjectImportSummary = {
  id: 'imp_failed',
  source_id: 'src_failed',
  status: 'extraction_failed',
  version: 2,
  failure_code: 'dependency_unavailable',
  failure_message: 'Project import extraction is temporarily unavailable.',
  retryable: true,
  created_at: '2026-08-19T10:00:00Z',
  updated_at: '2026-08-19T10:01:00Z',
  phase_count: 0,
  task_count: 0,
  material_count: 0,
  requirement_count: 0,
};

describe('project import API contract', () => {
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    setApiTokenProvider(async () => 'firebase-id-token');
  });

  afterEach(() => {
    if (originalApiBaseUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    setApiTokenProvider(null);
    vi.restoreAllMocks();
  });

  it('creates an import with the caller-owned retry claim', async () => {
    const input = {
      source_name: 'ridge-house.md',
      source_text: '# Foundation\nTask: Excavation',
      source_type: 'markdown' as const,
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'imp_ridge' }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await api.createProjectImport('prj_ridge', input, 'project-import:stable-claim');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects/prj_ridge/imports',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(input),
        headers: expect.objectContaining({ 'Idempotency-Key': 'project-import:stable-claim' }),
      }),
    );
  });

  it('lists bounded summaries and finds the latest nonterminal import', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [failedImport] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: [failedImport] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await api.listProjectImports('prj_ridge', { limit: 1, status: 'extraction_failed' })).toEqual([failedImport]);
    expect(await api.getLatestProjectImport('prj_ridge')).toEqual(failedImport);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/api/v1/projects/prj_ridge/imports?limit=1&status=extraction_failed',
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      'https://api.example.test/api/v1/projects/prj_ridge/imports?limit=1&nonterminal=true',
    );
  });
});
