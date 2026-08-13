'use client';

import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';

export function RecordDrawer({ title, eyebrow, onClose, children }: Readonly<{ title: string; eyebrow: string; onClose: () => void; children: React.ReactNode }>) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);

  useEffect(() => {
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    return () => returnFocus?.focus();
  }, []);

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') onClose();
    if (event.key !== 'Tab' || !drawer.current) return;
    const controls = [...drawer.current.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)')];
    if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  return <div className="record-drawer-backdrop" role="presentation" onMouseDown={onClose}><section ref={drawer} className="record-drawer" role="dialog" aria-modal="true" aria-labelledby="record-drawer-title" onMouseDown={(event) => event.stopPropagation()} onKeyDown={handleKeyDown}><header><div><span className="eyebrow">{eyebrow}</span><h2 id="record-drawer-title">{title}</h2></div><button ref={closeButton} className="icon-action" type="button" aria-label="Close details" onClick={onClose}><X size={20} aria-hidden="true" /></button></header><div className="record-drawer-body">{children}</div></section></div>;
}

export function RecordDetails({ items }: Readonly<{ items: Array<{ label: string; value: React.ReactNode }> }>) {
  return <dl className="record-details">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value || 'Not recorded'}</dd></div>)}</dl>;
}
