import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/src/lib/auth';

export const metadata: Metadata = {
  title: 'Oga Foreman — Keep the site moving',
  description: 'Tell Oga what happened on site. Oga handles the follow-through.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
