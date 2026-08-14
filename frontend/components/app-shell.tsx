'use client';

import {
  Activity,
  Bell,
  CalendarDays,
  Camera,
  ChevronDown,
  ClipboardList,
  FileClock,
  FileText,
  FolderOpen,
  HardHat,
  Home,
  ListTodo,
  LogOut,
  Menu,
  MessageSquareWarning,
  Package,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { OgConversation } from '@/components/og-conversation';
import type { Project } from '@/lib/api';
import { useAuth } from '@/src/lib/auth';

const navItems = [
  { label: 'Overview', suffix: '', icon: Home },
  { label: 'Schedule', suffix: '/schedule', icon: CalendarDays },
  { label: 'Tasks', suffix: '/tasks', icon: ListTodo },
  { label: 'Issues', suffix: '/issues', icon: MessageSquareWarning },
  { label: 'Materials', suffix: '/materials', icon: Package },
  { label: 'Daily Logs', suffix: '/daily-logs', icon: FileClock },
  { label: 'Photos', suffix: '/photos', icon: Camera },
  { label: 'Documents', suffix: '/documents', icon: FolderOpen },
  { label: 'Reports', suffix: '/reports', icon: FileText },
  { label: 'Activity', suffix: '/activity', icon: Activity },
] as const;

export function AppShell({ children, project, pendingApprovalCount = 0 }: Readonly<{ children: React.ReactNode; project: Project; pendingApprovalCount?: number }>) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuth();
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [moreOpen, setMoreOpen] = useState(false);
  const [askOgOpen, setAskOgOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const askOgButton = useRef<HTMLButtonElement>(null);
  const askOgTrigger = useRef<HTMLElement | null>(null);
  const askOgClose = useRef<HTMLButtonElement>(null);
  const askOgDrawer = useRef<HTMLElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const moreClose = useRef<HTMLButtonElement>(null);
  const moreSheet = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!askOgOpen) return;
    document.body.classList.add('overlay-open');
    askOgClose.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAskOgOpen(false);
    }
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      document.body.classList.remove('overlay-open');
    };
  }, [askOgOpen]);

  useEffect(() => {
    if (!moreOpen) return;
    document.body.classList.add('overlay-open');
    moreClose.current?.focus();
    return () => document.body.classList.remove('overlay-open');
  }, [moreOpen]);

  useEffect(() => {
    function openAskOg() {
      showAskOg();
    }
    window.addEventListener('og:open', openAskOg);
    return () => window.removeEventListener('og:open', openAskOg);
  }, []);

  function showAskOg() {
    askOgTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setAskOgOpen(true);
  }

  function closeAskOg() {
    setAskOgOpen(false);
    window.setTimeout(() => (askOgTrigger.current ?? askOgButton.current)?.focus(), 0);
  }

  function closeMore() {
    setMoreOpen(false);
    window.setTimeout(() => moreButton.current?.focus(), 0);
  }

  function containAskOgFocus(event: React.KeyboardEvent) {
    if (event.key !== 'Tab' || !askOgDrawer.current) return;
    const controls = [...askOgDrawer.current.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')];
    if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function containMoreFocus(event: React.KeyboardEvent) {
    if (event.key === 'Escape') { closeMore(); return; }
    if (event.key !== 'Tab' || !moreSheet.current) return;
    const controls = [...moreSheet.current.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]')];
    if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  async function signOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await auth.signOutUser();
      router.replace('/sign-in');
    } catch (cause) {
      setSignOutError(cause instanceof Error ? cause.message : 'OG could not sign you out. Try again.');
    } finally {
      setSigningOut(false);
    }
  }

  const isActive = (suffix: string) => suffix === ''
    ? pathname === `/projects/${projectId}`
    : pathname.startsWith(`/projects/${projectId}${suffix}`);
  const searchResults = searchQuery.trim()
    ? navItems.filter((item) => item.label.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : [];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#project-content">Skip to project content</a>
      <aside className="app-sidebar" aria-label="Project navigation">
        <Link className="logo-lockup project-brand" href="/projects" aria-label="OG Foreman projects">
          <span className="project-brand-mark" aria-hidden="true"><HardHat size={17} /></span>
          <span>OG Foreman</span>
        </Link>
        <ProjectSwitcher project={project} />
        <ProjectNavigation projectId={projectId} isActive={isActive} />
        <div className="app-sidebar-footer">
          <button ref={askOgButton} className="ask-og-button" type="button" onClick={showAskOg}>
            <Sparkles size={17} aria-hidden="true" /> Ask OG
          </button>
          <Link className="app-nav-link needs-you-link" href={`/projects/${projectId}/approvals`}>
            <Bell size={17} aria-hidden="true" />
            <span>Needs you</span>
            {pendingApprovalCount > 0 && <span className="notification-badge" aria-label={`${pendingApprovalCount} pending`}>{pendingApprovalCount}</span>}
          </Link>
        </div>
      </aside>

      <div className="app-main">
        <header className="project-topbar">
          <div className="mobile-project-identity">
            <span className="project-brand-mark" aria-hidden="true"><HardHat size={16} /></span>
            <span><strong>{project.name}</strong><small>OG Foreman</small></span>
          </div>
          <ProjectSearch query={searchQuery} results={searchResults} projectId={projectId} onQueryChange={setSearchQuery} />
          <div className="project-account-actions">
            <Link className="icon-action" href={`/projects/${projectId}/approvals`} aria-label={pendingApprovalCount ? `Needs you, ${pendingApprovalCount} pending` : 'Needs you'}>
              <Bell size={18} aria-hidden="true" />
              {pendingApprovalCount > 0 && <span className="notification-dot" aria-hidden="true" />}
            </Link>
            <button className="account-button" type="button" aria-label={signingOut ? 'Signing out' : 'Sign Out'} onClick={() => void signOut()} disabled={signingOut}>
              <span className="account-avatar" aria-hidden="true">OF</span>
              <span className="account-copy">{signingOut ? 'Signing out…' : 'Sign Out'}</span>
              <LogOut size={15} aria-hidden="true" />
            </button>
          </div>
          {signOutError ? <p className="auth-error shell-auth-error" role="alert">{signOutError}</p> : null}
        </header>

        <main className="app-content" id="project-content" tabIndex={-1}>{children}</main>
        <MobileNavigation projectId={projectId} isActive={isActive} onAskOg={showAskOg} onMore={() => setMoreOpen(true)} moreButton={moreButton} />
      </div>

      {moreOpen && (
        <div className="mobile-more-backdrop" role="presentation" onMouseDown={closeMore}>
          <section ref={moreSheet} className="mobile-more-sheet" role="dialog" aria-modal="true" aria-labelledby="more-navigation-title" onMouseDown={(event) => event.stopPropagation()} onKeyDown={containMoreFocus}>
            <div className="sheet-heading"><div><span className="eyebrow">Project</span><h2 id="more-navigation-title">More sections</h2></div><button ref={moreClose} className="icon-action" type="button" aria-label="Close more sections" onClick={closeMore}><X size={20} aria-hidden="true" /></button></div>
            <ProjectNavigation projectId={projectId} isActive={isActive} onNavigate={closeMore} label="All project sections" />
          </section>
        </div>
      )}

      {askOgOpen && (
        <div className="og-drawer-backdrop" role="presentation" onMouseDown={closeAskOg}>
          <section ref={askOgDrawer} className="og-drawer" role="dialog" aria-modal="true" aria-labelledby="ask-og-title" aria-describedby="ask-og-description" onMouseDown={(event) => event.stopPropagation()} onKeyDown={containAskOgFocus}>
            <div className="og-drawer-heading"><div><span className="eyebrow">Project assistant</span><h2 id="ask-og-title">Ask OG</h2><p id="ask-og-description">What&apos;s happening on site?</p></div><button ref={askOgClose} className="icon-action" type="button" aria-label="Close Ask OG" onClick={closeAskOg}><X size={20} /></button></div>
            <OgConversation projectId={projectId} />
          </section>
        </div>
      )}
    </div>
  );
}

function ProjectNavigation({ projectId, isActive, onNavigate, label = 'Project sections' }: Readonly<{ projectId: string; isActive: (suffix: string) => boolean; onNavigate?: () => void; label?: string }>) {
  return (
    <nav className="app-nav" aria-label={label}>
      {navItems.map(({ label: itemLabel, suffix, icon: Icon }) => (
        <Link className={`app-nav-link${isActive(suffix) ? ' active' : ''}`} href={`/projects/${projectId}${suffix}`} key={itemLabel} aria-current={isActive(suffix) ? 'page' : undefined} onClick={onNavigate}>
          <Icon size={17} aria-hidden="true" /><span>{itemLabel}</span>
        </Link>
      ))}
    </nav>
  );
}

function ProjectSearch({ query, results, projectId, onQueryChange }: Readonly<{ query: string; results: typeof navItems[number][]; projectId: string; onQueryChange: (value: string) => void }>) {
  return (
    <div className="project-search">
      <Search size={17} aria-hidden="true" />
      <label className="sr-only" htmlFor="project-search">Search project</label>
      <input id="project-search" type="search" value={query} placeholder="Search project" onChange={(event) => onQueryChange(event.target.value)} autoComplete="off" />
      {query.trim() && <div className="project-search-results" aria-label="Search results">{results.length ? results.map((item) => <Link href={`/projects/${projectId}${item.suffix}`} key={item.label} onClick={() => onQueryChange('')}><item.icon size={15} aria-hidden="true" />{item.label}</Link>) : <span>No matching project section.</span>}</div>}
    </div>
  );
}

function MobileNavigation({ projectId, isActive, onAskOg, onMore, moreButton }: Readonly<{ projectId: string; isActive: (suffix: string) => boolean; onAskOg: () => void; onMore: () => void; moreButton: React.RefObject<HTMLButtonElement | null> }>) {
  return <nav className="mobile-bottom-nav" aria-label="Mobile project navigation"><Link className={isActive('') ? 'active' : ''} href={`/projects/${projectId}`}><Home size={20} aria-hidden="true" /><span>Home</span></Link><Link className={isActive('/tasks') ? 'active' : ''} href={`/projects/${projectId}/tasks`}><ClipboardList size={20} aria-hidden="true" /><span>Tasks</span></Link><button className="mobile-og-action" type="button" onClick={onAskOg}><span><Sparkles size={20} aria-hidden="true" /></span><strong>OG</strong></button><Link className={isActive('/photos') ? 'active' : ''} href={`/projects/${projectId}/photos`}><Camera size={20} aria-hidden="true" /><span>Photos</span></Link><button ref={moreButton} type="button" onClick={onMore}><Menu size={20} aria-hidden="true" /><span>More</span></button></nav>;
}

function ProjectSwitcher({ project }: Readonly<{ project: Project }>) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="project-switcher-container">
      <button className={`project-switcher${isOpen ? ' active' : ''}`} type="button" aria-label={`Current project: ${project.name}`} aria-expanded={isOpen} onClick={() => setIsOpen(!isOpen)}>
        <span className="project-avatar" aria-hidden="true">{project.name.slice(0, 2).toUpperCase()}</span>
        <span className="project-switcher-copy"><strong>{project.name}</strong><span>{project.location}</span></span>
        <ChevronDown size={15} aria-hidden="true" className={`project-switcher-chevron${isOpen ? ' open' : ''}`} />
      </button>
      {isOpen && <div className="project-dropdown"><span className="dropdown-header">Current project</span><Link href={`/projects/${project.id}`} className="dropdown-item active" onClick={() => setIsOpen(false)}><span className="dropdown-item-content"><strong>{project.name}</strong><span>{project.location}</span></span></Link><Link className="dropdown-action" href="/projects">View all projects</Link></div>}
    </div>
  );
}
