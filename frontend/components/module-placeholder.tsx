import type { LucideIcon } from 'lucide-react';
import { PageHeader } from '@/components/page-header';

export function ModulePlaceholder({ title, description, emptyTitle, emptyDescription, icon: Icon }: Readonly<{ title: string; description: string; emptyTitle: string; emptyDescription: string; icon: LucideIcon }>) {
  return <div><PageHeader eyebrow="Project register" title={title} description={description} /><section className="module-placeholder" aria-labelledby="module-empty-title"><span className="module-placeholder-icon" aria-hidden="true"><Icon size={20} /></span><div><h2 id="module-empty-title">{emptyTitle}</h2><p>{emptyDescription}</p></div></section></div>;
}
