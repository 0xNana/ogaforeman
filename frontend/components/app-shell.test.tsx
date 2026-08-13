// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

describe('AppShell', () => {
  beforeEach(() => {
    replace.mockReset();
    signOutUser.mockReset();
    signOutUser.mockResolvedValue(undefined);
  });

  it('places Sign Out after Needs you and ends the session', async () => {
    render(
      <AppShell
        project={{ id: 'prj_ridge', name: 'Ridge House', location: 'East Legon', status: 'ACTIVE', timezone: 'Africa/Accra' }}
      >
        <p>Dashboard</p>
      </AppShell>,
    );

    const footer = screen.getByText('OG keeps watching unresolved work.').parentElement;
    expect(footer).not.toBeNull();
    const actions = Array.from((footer as HTMLElement).querySelectorAll('a, button'));
    expect(actions.map((action) => action.textContent?.trim())).toEqual(['Needs you', 'Sign Out']);

    fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));

    await waitFor(() => expect(signOutUser).toHaveBeenCalledOnce());
    expect(replace).toHaveBeenCalledWith('/sign-in');
  });
});
