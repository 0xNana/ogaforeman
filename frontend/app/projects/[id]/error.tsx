'use client';

import { AlertTriangle, RotateCcw } from 'lucide-react';

export default function ProjectError({ reset }: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return <div className="empty-state" role="alert"><span className="empty-state-icon"><AlertTriangle size={20} /></span><h2>We couldn&apos;t load this project.</h2><p>Nothing was changed. Try again, or check your connection.</p><button className="btn btn-primary btn-small" type="button" onClick={reset}><RotateCcw size={15} /> Try again</button></div>;
}
