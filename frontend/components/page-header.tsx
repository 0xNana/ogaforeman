import type { ReactNode } from 'react';

export function PageHeader({ eyebrow, title, description, actions }: Readonly<{ eyebrow?: string; title: string; description: string; actions?: ReactNode }>) {
  return <div className="page-heading"><div>{eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}<h1>{title}</h1><p>{description}</p></div>{actions ? <div className="page-heading-actions">{actions}</div> : null}</div>;
}
