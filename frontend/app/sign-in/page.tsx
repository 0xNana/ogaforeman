import { Suspense } from 'react';
import { AuthScreen } from '@/components/auth-screen';

export default function SignInPage() {
  return <Suspense><AuthScreen mode="sign-in" /></Suspense>;
}
