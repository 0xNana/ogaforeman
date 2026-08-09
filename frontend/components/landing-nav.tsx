'use client';

import { Menu, X } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

export function LandingNav() {
  const [open, setOpen] = useState(false);

  return (
    <header className={`site-nav${open ? ' mobile-open' : ''}`}>
      <div className="container site-nav-inner">
        <Link className="logo-lockup" href="/" aria-label="Oga Foreman home"><span className="logo-mark" aria-hidden="true" />Oga Foreman</Link>
        <nav className="site-nav-links" aria-label="Primary navigation">
          <a href="#how-it-works" onClick={() => setOpen(false)}>How it works</a>
          <a href="#capabilities" onClick={() => setOpen(false)}>What Oga handles</a>
          <a href="#teams" onClick={() => setOpen(false)}>For site teams</a>
          <Link href="/sign-in" onClick={() => setOpen(false)}>Sign in</Link>
        </nav>
        <div className="nav-actions"><Link href="/sign-up" className="btn btn-primary btn-small">Start free</Link><button className="nav-menu-button" type="button" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? <X size={19} /> : <Menu size={19} />}</button></div>
      </div>
    </header>
  );
}
