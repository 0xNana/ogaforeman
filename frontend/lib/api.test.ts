import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiConfigurationError, ApiRequestError, api, demoApi, setApiTokenProvider } from './api';


describe('production API boundary', () => {
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const originalDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_DEMO_MODE;
    setApiTokenProvider(async () => 'firebase-id-token');
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    if (originalApiBaseUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    if (originalDemoMode === undefined) delete process.env.NEXT_PUBLIC_DEMO_MODE;
    else process.env.NEXT_PUBLIC_DEMO_MODE = originalDemoMode;
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

  it('serves fixture state only when demo mode is explicit', async () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';

    const snapshot = demoApi.getProjectSnapshot('prj_demo');

    expect(snapshot.project.id).toBe('prj_demo');
    expect(snapshot.project.name).toBe('Ridge House');
    expect(snapshot.tasks.length).toBeGreaterThan(0);
  });

  it('does not use demo fixtures for authenticated project requests', async () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    await expect(api.getProjectSnapshot('prj_demo')).rejects.toBeInstanceOf(
      ApiConfigurationError,
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

  it('submits site updates with the accepted contract and an idempotency key', async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.test';
    const accepted = {
      site_update_id: 'sup_update123',
      event_id: 'evt_update123',
      agent_run_id: 'run_update123',
      status: 'queued' as const,
      status_url: '/api/v1/projects/prj_ridge/agent-runs/run_update123',
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(accepted), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.submitSiteUpdate('prj_ridge', '  Blockwork is done.  ')).resolves.toEqual(
      accepted,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects/prj_ridge/site-updates',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ raw_text: 'Blockwork is done.' }),
        headers: expect.objectContaining({
          Authorization: 'Bearer firebase-id-token',
          'Idempotency-Key': expect.stringMatching(/^site-update:/),
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
      requestedBy: 'Oga',
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
