'use client';

import { ArrowRight, HardHat, LoaderCircle } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useState } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/src/lib/auth';

export function AuthScreen({ mode }: Readonly<{ mode: 'sign-in' | 'sign-up' }>) {
  const auth = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [resetSent, setResetSent] = useState(false);
  const isSignUp = mode === 'sign-up';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    auth.clearError();
    setSubmitError(null);
    try {
      if (isSignUp) await auth.signUp(email, password, displayName);
      else await auth.signIn(email, password);
      await api.bootstrapUser(isSignUp ? displayName : undefined);
      const next = safeNextPath(searchParams.get('next'));
      router.replace(next ?? '/projects');
    } catch (cause) {
      setSubmitError(cause instanceof Error ? cause.message : 'OG could not complete sign-in. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (!email.trim()) return;
    setBusy(true);
    try {
      await auth.resetPassword(email);
      setResetSent(true);
    } catch {
      setResetSent(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <Link className="logo-lockup auth-logo" href="/" aria-label="OG Foreman home">
        <span className="logo-mark" aria-hidden="true" />OG Foreman
      </Link>
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-intro">
          <span className="auth-icon" aria-hidden="true"><HardHat size={20} /></span>
          <span className="eyebrow">{isSignUp ? 'Put OG on your site' : 'Welcome back'}</span>
          <h1 id="auth-title">{isSignUp ? 'Start with one site update.' : 'Keep the site moving.'}</h1>
          <p>{isSignUp
            ? 'Create your account, open a project and tell OG what happened.'
            : 'Sign in to see what changed, what is blocked and what needs you.'}</p>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {isSignUp ? <label>Full name<input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={200} /></label> : null}
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>Password<input type="password" autoComplete={isSignUp ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} /></label>

          {auth.error || submitError ? <p className="auth-error" role="alert">{auth.error?.message ?? submitError}</p> : null}
          {resetSent ? <p className="auth-success" role="status">Password reset email sent.</p> : null}

          <button className="btn btn-primary btn-block" type="submit" disabled={busy || auth.state === 'unavailable'}>
            {busy ? <LoaderCircle className="spin-icon" size={17} /> : null}
            {isSignUp ? 'Create account' : 'Sign in'} <ArrowRight size={16} />
          </button>

          {!isSignUp ? <button className="auth-text-button" type="button" onClick={resetPassword} disabled={busy || !email.trim()}>Forgot your password?</button> : null}
        </form>

        <p className="auth-switch">{isSignUp ? 'Already using OG?' : 'New to OG?'}{' '}
          <Link href={isSignUp ? '/sign-in' : '/sign-up'}>{isSignUp ? 'Sign in' : 'Create an account'}</Link>
        </p>
        <Link className="auth-demo-link" href="/demo">See OG in action without signing in →</Link>
      </section>
    </main>
  );
}

function safeNextPath(value: string | null): string | null {
  return value?.startsWith('/') && !value.startsWith('//') ? value : null;
}
