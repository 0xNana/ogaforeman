import { ProjectSetupHandoff } from '@/components/project-setup-handoff';

export default async function ProjectSetupPage({ params, searchParams }: Readonly<{
  params: Promise<{ id: string }>;
  searchParams: Promise<{ method?: string }>;
}>) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const method = query.method === 'empty' ? 'empty' : 'import';
  return <ProjectSetupHandoff projectId={id} method={method} />;
}
