// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthScreen } from './auth-screen';

const { bootstrapUser, clearError, replace, signIn } = vi.hoisted(() => ({
  bootstrapUser: vi.fn(),
  clearError: vi.fn(),
  replace: vi.fn(),
  signIn: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/api', () => ({
  api: { bootstrapUser },
}));

vi.mock('@/src/lib/auth', () => ({
  useAuth: () => ({
    clearError,
    error: null,
    resetPassword: vi.fn(),
    signIn,
    signUp: vi.fn(),
    state: 'signed_out',
  }),
}));

describe('AuthScreen', () => {
  beforeEach(() => {
    bootstrapUser.mockReset();
    clearError.mockReset();
    replace.mockReset();
    signIn.mockReset();
    signIn.mockResolvedValue(undefined);
  });

  it('shows a bootstrap failure after Firebase sign-in succeeds', async () => {
    bootstrapUser.mockRejectedValue(new Error('OG could not reach the project service.'));
    render(<AuthScreen mode="sign-in" />);

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'manager@example.test' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'local-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'OG could not reach the project service.',
    );
    expect(replace).not.toHaveBeenCalled();
  });
});
