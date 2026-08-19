// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ProjectsPage from './page';

const { listProjects } = vi.hoisted(() => ({ listProjects: vi.fn() }));

vi.mock('@/lib/api', () => ({ api: { listProjects } }));
vi.mock('@/src/lib/auth', () => ({
  useAuth: () => ({ state: 'authenticated' }),
}));

describe('ProjectsPage project creation entry points', () => {
  afterEach(cleanup);

  beforeEach(() => {
    listProjects.mockReset();
  });

  it('routes the project-list action into the dedicated wizard', async () => {
    listProjects.mockResolvedValue([
      { id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' },
    ]);

    render(<ProjectsPage />);

    expect(await screen.findByRole('link', { name: 'New project' })).toHaveAttribute('href', '/projects/new');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('routes first-project onboarding into the same wizard', async () => {
    listProjects.mockResolvedValue([]);

    render(<ProjectsPage />);

    expect(await screen.findByRole('link', { name: 'Create your first project' })).toHaveAttribute('href', '/projects/new');
  });
});
