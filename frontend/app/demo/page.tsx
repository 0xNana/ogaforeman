import Link from 'next/link';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { OgaDemo } from '@/components/oga-demo';

export default function DemoPage() {
  return (
    <main className="demo-page">
      <div className="container demo-page-top">
        <Link className="logo-lockup" href="/"><span className="logo-mark" aria-hidden="true" />Oga Foreman</Link>
        <Link className="btn btn-quiet btn-small" href="/"><ArrowLeft size={15} /> Back</Link>
      </div>
      <section className="container demo-page-grid">
        <div className="display-copy">
          <span className="eyebrow">Oga in action</span>
          <h1>One update. The follow-through handled.</h1>
          <p>This is a public, deterministic product demonstration. It does not read or write a real project.</p>
          <Link className="btn btn-accent" href="/sign-up">Start a real project <ArrowRight size={17} /></Link>
        </div>
        <OgaDemo />
      </section>
    </main>
  );
}
