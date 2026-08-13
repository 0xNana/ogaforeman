'use client';

import { AlertTriangle, Check, CheckCircle2, LoaderCircle, PackageCheck } from 'lucide-react';
import { useEffect, useState } from 'react';

const steps = [
  { label: 'Blockwork', copy: 'Marked complete', icon: CheckCircle2, tone: 'done' },
  { label: 'Electrical', copy: 'Blocker found', icon: AlertTriangle, tone: 'warn' },
  { label: 'Cement', copy: 'Running low', icon: AlertTriangle, tone: 'warn' },
  { label: 'Follow-through', copy: 'Request prepared', icon: PackageCheck, tone: 'done' },
  { label: 'Daily report', copy: 'Updated for today', icon: Check, tone: 'done' },
];

export function OgaDemo() {
  const [activeStep, setActiveStep] = useState(steps.length);

  useEffect(() => {
    const timer = window.setInterval(() => setActiveStep(step => (step + 1) % (steps.length + 1)), 1600);
    return () => window.clearInterval(timer);
  }, []);

  const isProcessing = activeStep === 0;
  return (
    <div id="demo" className="demo-frame" aria-label="Interactive OG product demonstration">
      <div className="demo-window">
        <div className="demo-window-bar"><span className="window-dot" /><span className="window-dot" /><span className="window-dot" /><span className="demo-window-label">Ridge House · Today</span></div>
        <div className="demo-content">
          <div className="demo-message"><span className="demo-label">Foreman</span><p className="demo-quote">“First-floor blockwork is done. The electrician didn&apos;t show and we&apos;re almost out of cement.”</p><div className="demo-meta"><span className="avatar">K</span><span>Kwame · 09:38</span></div></div>
          <div className="demo-result"><div className="demo-result-head"><span className="demo-result-title">OG</span><span className="demo-live"><span className="live-dot" />{isProcessing ? 'Listening' : 'Handled'}</span></div>{isProcessing ? <div className="demo-step" style={{ marginTop: '22px' }}><span className="demo-step-icon needs"><LoaderCircle size={14} className="spin-icon" /></span><div className="demo-step-copy"><strong>Understanding site update...</strong><span>Checking what changed.</span></div></div> : <><div className="demo-steps">{steps.slice(0, activeStep).map(({ label, copy, icon: Icon, tone }, index) => <div className="demo-step" style={{ animationDelay: `${index * 55}ms` }} key={label}><span className={`demo-step-icon ${tone}`}><Icon size={14} /></span><div className="demo-step-copy"><strong>{label}</strong><span>{copy}</span></div></div>)}</div>{activeStep >= steps.length && <div className="demo-approval"><span><strong>Needs you</strong><span>Approve cement request · 100 bags</span></span><span aria-hidden="true">→</span></div>}</>}</div>
        </div>
      </div>
    </div>
  );
}
