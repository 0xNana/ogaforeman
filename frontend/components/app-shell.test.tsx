// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from './app-shell';

const { replace, signOutUser } = vi.hoisted(() => ({
  replace: vi.fn(),
  signOutUser: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'prj_ridge' }),
  usePathname: () => '/projects/prj_ridge',
  useRouter: () => ({ replace }),
}));

vi.mock('@/src/lib/auth', () => ({
  useAuth: () => ({ signOutUser }),
}));

vi.mock('@/components/site-composer', () => ({
  SiteComposer: () => <div>Site composer</div>,
}));

describe('AppShell', () => {
  afterEach(cleanup);

  beforeEach(() => {
    replace.mockReset();
    signOutUser.mockReset();
    signOutUser.mockResolvedValue(undefined);
  });

  it('renders the locked construction navigation and global shell controls', () => {
    render(
      <AppShell
        project={{ id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' }}
      >
        <p>Overview content</p>
      </AppShell>,
    );

    const navigation = screen.getByRole('navigation', { name: 'Project sections' });
    expect(Array.from(navigation.querySelectorAll('a')).map((link) => link.textContent?.trim())).toEqual([
      'Overview',
      'Schedule',
      'Tasks',
      'Issues',
      'Materials',
      'Daily Logs',
      'Photos',
      'Documents',
      'Reports',
      'Activity',
    ]);
    expect(screen.getByRole('searchbox', { name: 'Search project' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Ask OG' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Skip to project content' })).toHaveAttribute('href', '#project-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'project-content');
  });

  it('opens and closes the Ask OG panel with accessible dialog semantics', () => {
    render(
      <AppShell
        project={{ id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' }}
      >
        <p>Overview content</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Ask OG' }));
    expect(screen.getByRole('dialog', { name: 'Ask OG' })).toBeVisible();
    expect(screen.getByRole('dialog', { name: 'Ask OG' })).toHaveAttribute('aria-describedby', 'ask-og-description');
    expect(screen.getByText('Site composer')).toBeVisible();
    expect(document.body).toHaveClass('overlay-open');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Ask OG' })).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass('overlay-open');
  });

  it('opens Ask OG from a field-screen shortcut', () => {
    render(
      <AppShell project={{ id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' }}>
        <p>Overview content</p>
      </AppShell>,
    );

    act(() => window.dispatchEvent(new Event('og:open')));
    expect(screen.getByRole('dialog', { name: 'Ask OG' })).toBeVisible();
  });

  it('ends the session from the account action', async () => {
    render(
      <AppShell
        project={{ id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' }}
      >
        <p>Overview content</p>
      </AppShell>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));

    await waitFor(() => expect(signOutUser).toHaveBeenCalledOnce());
    expect(replace).toHaveBeenCalledWith('/sign-in');
  });
});
