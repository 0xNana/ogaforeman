'use client';

import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
  type User,
} from 'firebase/auth';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getFirebaseAuth } from './firebase';

export type AuthState = 'loading' | 'authenticated' | 'signed_out' | 'unavailable';

export type AuthActionError = {
  code: string;
  message: string;
};

type AuthContextValue = {
  user: User | null;
  state: AuthState;
  error: AuthActionError | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  signOutUser: () => Promise<void>;
  clearError: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [user, setUser] = useState<User | null>(null);
  const [state, setState] = useState<AuthState>('loading');
  const [error, setError] = useState<AuthActionError | null>(null);

  useEffect(() => {
    try {
      return onAuthStateChanged(getFirebaseAuth(), (nextUser) => {
        setUser(nextUser);
        setState(nextUser ? 'authenticated' : 'signed_out');
      });
    } catch (cause) {
      queueMicrotask(() => {
        setState('unavailable');
        setError(toAuthError(cause));
      });
      return undefined;
    }
  }, []);

  const run = useCallback(async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (cause) {
      const nextError = toAuthError(cause);
      setError(nextError);
      throw nextError;
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    state,
    error,
    signIn: (email, password) => run(async () => {
      await signInWithEmailAndPassword(getFirebaseAuth(), email.trim(), password);
    }),
    signUp: (email, password, displayName) => run(async () => {
      const result = await createUserWithEmailAndPassword(getFirebaseAuth(), email.trim(), password);
      if (displayName.trim()) await updateProfile(result.user, { displayName: displayName.trim() });
    }),
    resetPassword: (email) => run(() => sendPasswordResetEmail(getFirebaseAuth(), email.trim())),
    signOutUser: () => run(() => signOut(getFirebaseAuth())),
    clearError: () => setError(null),
  }), [error, run, state, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

function toAuthError(cause: unknown): AuthActionError {
  const code = typeof cause === 'object' && cause && 'code' in cause
    ? String((cause as { code: string }).code)
    : 'auth/unavailable';
  const messages: Record<string, string> = {
    'auth/invalid-credential': 'That email or password is not right.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/email-already-in-use': 'An account already exists for that email.',
    'auth/weak-password': 'Use a password with at least six characters.',
    'auth/network-request-failed': 'Connection failed. Check your network and try again.',
    'auth/too-many-requests': 'Too many attempts. Wait a moment, then try again.',
    'auth/user-disabled': 'This account is disabled. Contact your project administrator.',
    'auth/unavailable': 'Sign-in is not configured for this environment yet.',
  };
  return { code, message: messages[code] ?? 'OG could not complete that request. Try again.' };
}
