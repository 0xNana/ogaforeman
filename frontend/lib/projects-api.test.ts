import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, setApiTokenProvider } from './api';

describe('projects API contract', () => {
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

  it('sends complete project details with the caller-owned retry key', async () => {
    const input = {
      name: 'Ridge House',
      location: 'East Legon',
      description: 'Residential build',
      timezone: 'Africa/Accra',
      start_date: '2026-09-01',
      target_end_date: '2027-04-30',
      status: 'planning' as const,
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'prj_ridge' }), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await api.createProject(input, 'project:stable-retry-claim');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/projects',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(input),
        headers: expect.objectContaining({ 'Idempotency-Key': 'project:stable-retry-claim' }),
      }),
    );
  });
});
