import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiConfigurationError, ApiRequestError, api, setApiTokenProvider } from './api';


describe('production API boundary', () => {
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    setApiTokenProvider(async () => 'firebase-id-token');
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    if (originalApiBaseUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    vi.restoreAllMocks();
    setApiTokenProvider(null);
  });

  it('fails closed when production mode has no API base URL', async () => {
    await expect(api.getProjectSnapshot('prj_ridge')).rejects.toBeInstanceOf(
      ApiConfigurationError,
    );
  });

  it('returns API state without substituting demo data', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const response = {
      project: {
        id: 'prj_remote',
        name: 'Remote Project',
        location: 'Accra',
        status: 'ACTIVE' as const,
        timezone: 'Africa/Accra',
      },
      tasks: [],
      materials: [],
      approvals: [],
      activities: [],
      report: {
        date: 'Saturday, 8 August',
        completed: [],
        inProgress: [],
        blocked: [],
        materials: [],
        tomorrow: [],
        risks: [],
        photos: [],
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.getProjectSnapshot('prj_remote')).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects/prj_remote/snapshot',
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer firebase-id-token' }),
      }),
    );
  });

  it('surfaces non-success API responses', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'AUTH_REQUIRED' } }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(api.getProject('prj_ridge')).rejects.toSatisfy((error: unknown) => {
      return (
        error instanceof ApiRequestError &&
        error.status === 401 &&
        error.code === 'AUTH_REQUIRED'
      );
    });
  });

  it('creates canonical task and material resources with authenticated idempotent requests', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'tsk_new' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'mat_new' }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await api.createTask('prj_ridge', { title: 'First-floor blockwork' });
    await api.createMaterial('prj_ridge', {
      name: 'Cement',
      unit: 'bags',
      available_quantity: 20,
      minimum_required_quantity: 10,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(1,
      'https://api.example.test/api/v1/projects/prj_ridge/tasks',
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer firebase-id-token', 'Idempotency-Key': expect.any(String) }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      'https://api.example.test/api/v1/projects/prj_ridge/materials',
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer firebase-id-token', 'Idempotency-Key': expect.any(String) }) }),
    );
  });

  it('loads and decides a project import through its review-only API contract', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const review = { id: 'imp_ridge', source_id: 'src_ridge', status: 'needs_review', version: 3 };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(review), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...review, status: 'imported', version: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...review, status: 'cancelled', version: 4 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await api.getProjectImport('prj_ridge', 'imp_ridge');
    await api.confirmProjectImport('prj_ridge', 'imp_ridge', 3, 'project-import-confirm:stable');
    await api.cancelProjectImport('prj_ridge', 'imp_ridge', 3, 'project-import-cancel:stable');

    expect(fetchMock).toHaveBeenNthCalledWith(1,
      'https://api.example.test/api/v1/projects/prj_ridge/imports/imp_ridge',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer firebase-id-token' }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      'https://api.example.test/api/v1/projects/prj_ridge/imports/imp_ridge/confirm',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ expected_version: 3 }), headers: expect.objectContaining({ 'Idempotency-Key': 'project-import-confirm:stable' }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(3,
      'https://api.example.test/api/v1/projects/prj_ridge/imports/imp_ridge/cancel',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ expected_version: 3 }), headers: expect.objectContaining({ 'Idempotency-Key': 'project-import-cancel:stable' }) }),
    );
  });

  it('refreshes the Firebase token once after an unauthorized response', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const tokens: boolean[] = [];
    setApiTokenProvider(async (forceRefresh = false) => {
      tokens.push(forceRefresh);
      return forceRefresh ? 'refreshed-token' : 'stale-token';
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'prj_ridge' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    vi.stubGlobal('fetch', fetchMock);

    await api.getProject('prj_ridge');

    expect(tokens).toEqual([false, true]);
    expect(fetchMock).toHaveBeenLastCalledWith(
      'https://api.example.test/api/v1/projects/prj_ridge',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer refreshed-token' }),
      }),
    );
  });

  it('fails before a protected request when no authenticated session exists', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    setApiTokenProvider(async () => null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.getProject('prj_ridge')).rejects.toSatisfy((error: unknown) => (
      error instanceof ApiRequestError && error.code === 'AUTH_REQUIRED'
    ));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('submits multimodal input through the universal conversation contract', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const accepted = {
      kind: 'workflow',
      text: 'I saved the update and started the site workflow.',
      cited_record_ids: [],
      mutation_performed: false,
      site_update_id: 'sup_update123',
      event_id: 'evt_update123',
      workflow_run_id: 'run_update123',
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(accepted), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.sendConversationMessage(
      'prj_ridge',
      'Blockwork is done.',
      'conversation:stable-retry',
      { attachmentIds: ['att_photo123'], inputType: 'mixed' },
    )).resolves.toEqual(accepted);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects/prj_ridge/conversations/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          message: 'Blockwork is done.',
          attachment_ids: ['att_photo123'],
          input_type: 'mixed',
        }),
        headers: expect.objectContaining({
          Authorization: 'Bearer firebase-id-token',
          'Idempotency-Key': 'conversation:stable-retry',
        }),
      }),
    );
  });

  it('resolves approvals through the decision endpoint with optimistic concurrency', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const response = {
      id: 'apr_cement123',
      type: 'Purchase',
      title: 'Cement request',
      status: 'APPROVED' as const,
      quantity: '30 bags',
      neededBy: 'Tomorrow',
      reason: 'Cement is needed for plastering.',
      requestedBy: 'OG',
      date: '8 Aug, 09:45',
      version: 1,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      api.resolveApproval('prj_ridge', 'apr_cement123', 'APPROVE', 0),
    ).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects/prj_ridge/approvals/apr_cement123/decision',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ decision: 'approved', expected_version: 0 }),
        headers: expect.objectContaining({
          Authorization: 'Bearer firebase-id-token',
          'Idempotency-Key': expect.stringMatching(/^approval:/),
        }),
      }),
    );
  });
});
