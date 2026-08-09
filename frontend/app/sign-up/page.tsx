import { Suspense } from 'react';
import { AuthScreen } from '@/components/auth-screen';

export default function SignUpPage() {
  return <Suspense><AuthScreen mode="sign-up" /></Suspense>;
}
