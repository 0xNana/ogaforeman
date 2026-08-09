'use client';

import { SiteComposer } from '@/components/site-composer';
import { useParams } from 'next/navigation';

export default function SitePage() {
  const { id } = useParams<{ id: string }>();
  return <SiteComposer projectId={id} />;
}
