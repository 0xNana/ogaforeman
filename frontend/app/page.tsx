import Link from 'next/link';
import {
  ArrowRight,
  BellRing,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Flag,
  HardHat,
  Image as ImageIcon,
  ListChecks,
  MessageSquareText,
  PackageCheck,
  Play,
  ShieldCheck,
  Smartphone,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import { LandingNav } from '@/components/landing-nav';
import { OgaDemo } from '@/components/oga-demo';
import { siteUpdateSteps } from '@/components/site-update-steps';

const capabilities = [
  { title: 'Daily site updates', copy: 'Voice notes and photos become useful project context.', icon: MessageSquareText },
  { title: 'Progress', copy: 'Tell OG what is finished. Your status stays current.', icon: CheckCircle2 },
  { title: 'Blockers', copy: 'See what is stuck—and what gets delayed next.', icon: Flag },
  { title: 'Materials', copy: 'Running low? OG catches the risk early.', icon: PackageCheck },
  { title: 'Daily reports', copy: 'The day becomes a clean report without the desk work.', icon: FileText },
  { title: 'Approvals', copy: 'Routine work moves. Important decisions come back to you.', icon: ShieldCheck },
  { title: 'Daily brief', copy: 'Start with what is done, late and waiting.', icon: BellRing },
  { title: 'Activity', copy: 'See what changed, why, and what still needs action.', icon: ListChecks },
];

const beforeItems = [
  'Voice notes buried in chats',
  'Site photos with no context',
  'Someone manually updating progress',
  'Material shortages found too late',
  'Hours spent writing daily reports',
  'Managers chasing every follow-up',
];

const afterItems = [
  'Every update becomes project context',
  'Photos stay attached to what happened',
  'Progress updates from site reports',
  'Material risks surface before they stop work',
  'Daily reports write themselves',
  'Follow-ups stay visible until resolved',
];

const flow = [
  ['Site update', 'Say what happened'],
  ['Understand', 'Find the useful facts'],
  ['Check project', 'See what it affects'],
  ['Update progress', 'Keep the record current'],
  ['Find blocker', 'Surface what is stuck'],
  ['Prepare action', 'Get the next step ready'],
  ['Need approval?', 'Bring it to you'],
  ['Watch next', 'Keep following through'],
];

export default function HomePage() {
  return (
    <div>
      <LandingNav />

      <main id="main-content">
        <section className="hero">
          <div className="container hero-grid">
            <div className="display-copy">
              <span className="eyebrow">Your AI construction site coordinator</span>
              <h1>Your site doesn&apos;t need <em>another dashboard.</em></h1>
              <p className="hero-lede">Tell OG what happened. Keep the site moving.</p>
              <p className="hero-support">
                Send a voice note, photo or site update. OG turns it into progress, follow-ups, material requests and a daily report.
              </p>
              <div className="hero-actions">
                <Link href="/sign-up" className="btn btn-accent">Start a project — Free <ArrowRight size={17} /></Link>
                <Link href="/demo" className="btn btn-quiet"><Play size={15} fill="currentColor" /> See OG in action</Link>
              </div>
              <p className="microcopy">Free to use. No card required.</p>
            </div>
            <OgaDemo />
          </div>
        </section>

        <section className="trust-strip" aria-label="Who OG is built for">
          <div className="container trust-inner">
            <span className="trust-label">Built for the people keeping sites moving</span>
            <div className="trust-list"><span>Foremen</span><span>Site managers</span><span>Contractors</span><span>Project managers</span><span>Builders</span></div>
          </div>
        </section>

        <section id="capabilities" className="section capabilities">
          <div className="container">
            <div className="section-heading">
              <div><span className="eyebrow">What OG handles</span><h2>One update. A lot less chasing.</h2></div>
              <p>OG understands what is happening on site, figures out what it affects, and handles the routine follow-through.</p>
            </div>
            <div className="capability-grid">
              {capabilities.map(({ title, copy, icon: Icon }) => (
                <article className="capability-card" key={title}>
                  <span className="capability-icon"><Icon size={18} /></span>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="section product-moment">
          <div className="container moment-grid">
            <div className="phone-shell" aria-label="OG mobile composer preview">
              <div className="phone-screen">
                <div className="phone-status"><span>9:41</span><span>● ● ●</span></div>
                <h3>Good morning.</h3>
                <p>What&apos;s happening on site?</p>
                <div className="phone-composer">
                  <span className="phone-composer-copy">Hold to talk to OG</span>
                  <span className="phone-mic"><Smartphone size={27} /></span>
                  <button className="phone-add" type="button"><ImageIcon size={15} /> Add site photos</button>
                </div>
                <div className="phone-today"><span className="phone-today-label">Today</span>
                  <div className="phone-today-item"><Check size={15} /> Blockwork completed</div>
                  <div className="phone-today-item warn"><TriangleAlert size={15} /> Cement running low</div>
                  <div className="phone-today-item warn"><TriangleAlert size={15} /> Electrician follow-up pending</div>
                </div>
              </div>
            </div>
            <div className="moment-copy">
              <span className="eyebrow">From site update to site action</span>
              <h2>Say it once. OG takes it from there.</h2>
              <p>The fastest way to update OG is the way site teams already work—talk, snap a photo and keep moving.</p>
              <div className="process-list">
                {siteUpdateSteps.map(({ number, label, copy }) => <div className="process-row" key={number}><span className="process-number">{number}</span><div><strong>{label}</strong><span>{copy}</span></div></div>)}
              </div>
            </div>
          </div>
        </section>

        <section className="section comparison">
          <div className="container">
            <span className="eyebrow">Before OG / With OG</span>
            <h2>Construction moves fast. The paperwork should too.</h2>
            <div className="comparison-grid">
              <div className="comparison-panel before"><h3>Before OG</h3><ul className="comparison-list">{beforeItems.map(item => <li key={item}><span aria-hidden="true">—</span>{item}</li>)}</ul></div>
              <div className="comparison-panel after"><h3>With OG</h3><ul className="comparison-list">{afterItems.map(item => <li key={item}><CheckCircle2 size={17} />{item}</li>)}</ul></div>
            </div>
          </div>
        </section>

        <section className="section autonomy">
          <div className="container">
            <div className="autonomy-copy"><span className="eyebrow">From update to follow-through</span><h2>OG turns site updates into next steps.</h2><p>It records progress, flags blockers, keeps materials in view and prepares the follow-up so the project record stays current.</p></div>
            <div className="autonomy-flow" aria-label="How OG follows through">{flow.map(([title, copy]) => <div className="flow-step" key={title}><strong>{title}</strong><span>{copy}</span></div>)}</div>
          </div>
        </section>

        <section className="section control">
          <div className="container control-grid">
            <div className="control-copy"><span className="eyebrow">Human control</span><h2>OG handles the routine. You keep the final say.</h2><p>Progress updates, reports and follow-ups can happen automatically. Purchases, major schedule changes and other consequential actions come back to you first.</p></div>
            <div className="approval-card"><div className="approval-card-top"><span className="approval-label">Approval required</span><span className="approval-status"><TriangleAlert size={14} /> Needs you</span></div><h3>Cement request</h3><div className="approval-details"><div><span className="approval-detail-label">OG recommends</span><strong className="approval-detail-value">100 bags</strong></div><div><span className="approval-detail-label">Needed for</span><strong className="approval-detail-value">Plastering</strong></div><div><span className="approval-detail-label">Needed by</span><strong className="approval-detail-value">Tomorrow</strong></div></div><p className="approval-reason">Current stock may not cover tomorrow&apos;s planned work.</p><div className="approval-actions"><button className="btn btn-primary" type="button">Approve</button><button className="btn btn-quiet" type="button">Reject</button></div></div>
          </div>
        </section>

        <section id="teams" className="section mobile-section">
          <div className="container mobile-grid">
            <div className="mobile-copy"><span className="eyebrow">Built for the site</span><h2>No laptop required.</h2><p>Talk, snap a photo and keep moving. OG gives the whole team one clear view of what changed.</p><div className="mobile-notes"><span className="mobile-note"><HardHat size={17} /> Voice-first updates for the field</span><span className="mobile-note"><Sparkles size={17} /> Calm, useful follow-through</span><span className="mobile-note"><ShieldCheck size={17} /> Important actions stay yours</span></div></div>
            <div className="mobile-visual"><div className="phone-shell"><div className="phone-screen"><div className="phone-status"><span>9:41</span><span>● ● ●</span></div><h3>What&apos;s happening on site?</h3><div className="phone-composer"><span className="phone-composer-copy">Hold to talk to OG</span><span className="phone-mic"><MessageSquareText size={26} /></span><button className="phone-add" type="button"><ImageIcon size={15} /> Add site photos</button></div><div className="phone-today"><span className="phone-today-label">Today</span><div className="phone-today-item"><Check size={15} /> Blockwork completed</div><div className="phone-today-item warn"><TriangleAlert size={15} /> Cement running low</div></div></div></div></div>
          </div>
        </section>

        <section className="free-section"><div className="container"><h2>Put OG to work. It&apos;s free.</h2><p>Create a project, send site updates and let OG handle the follow-through.</p><Link href="/sign-up" className="btn">Start free <ArrowRight size={17} /></Link><p className="microcopy">No card required.</p></div></section>
        <section className="final-cta"><div className="container"><h2>Less chasing. More building.</h2><p>Tell OG what&apos;s happening on site and get back to the work that matters.</p><div className="final-actions"><Link href="/sign-up" className="btn">Start a project — Free <ArrowRight size={17} /></Link><Link href="/demo" className="btn btn-quiet">See how OG works</Link></div></div></section>
      </main>
      <footer className="footer"><div className="container footer-inner"><span>© 2026 OG Foreman</span><span>Talk to OG. Keep the site moving.</span></div></footer>
    </div>
  );
}
