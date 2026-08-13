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
import { SiteComposer } from '@/components/site-composer';
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
  const askOgClose = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!askOgOpen) return;
    askOgClose.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAskOgOpen(false);
    }
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [askOgOpen]);

  function closeAskOg() {
    setAskOgOpen(false);
    window.setTimeout(() => askOgButton.current?.focus(), 0);
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
          <button ref={askOgButton} className="ask-og-button" type="button" onClick={() => setAskOgOpen(true)}>
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
            <button className="account-button" type="button" onClick={() => void signOut()} disabled={signingOut}>
              <span className="account-avatar" aria-hidden="true">OF</span>
              <span className="account-copy">{signingOut ? 'Signing out…' : 'Sign Out'}</span>
              <LogOut size={15} aria-hidden="true" />
            </button>
          </div>
          {signOutError ? <p className="auth-error shell-auth-error" role="alert">{signOutError}</p> : null}
        </header>

        <main className="app-content" id="project-content" tabIndex={-1}>{children}</main>
        <MobileNavigation projectId={projectId} isActive={isActive} onAskOg={() => setAskOgOpen(true)} onMore={() => setMoreOpen(true)} />
      </div>

      {moreOpen && (
        <div className="mobile-more-backdrop" role="presentation" onMouseDown={() => setMoreOpen(false)}>
          <section className="mobile-more-sheet" role="dialog" aria-modal="true" aria-labelledby="more-navigation-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="sheet-heading"><div><span className="eyebrow">Project</span><h2 id="more-navigation-title">More sections</h2></div><button className="icon-action" type="button" aria-label="Close more sections" onClick={() => setMoreOpen(false)}><X size={20} /></button></div>
            <ProjectNavigation projectId={projectId} isActive={isActive} onNavigate={() => setMoreOpen(false)} label="All project sections" />
          </section>
        </div>
      )}

      {askOgOpen && (
        <div className="og-drawer-backdrop" role="presentation" onMouseDown={closeAskOg}>
          <section className="og-drawer" role="dialog" aria-modal="true" aria-labelledby="ask-og-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="og-drawer-heading"><div><span className="eyebrow">Site update</span><h2 id="ask-og-title">Ask OG</h2><p>Tell OG what is happening on site.</p></div><button ref={askOgClose} className="icon-action" type="button" aria-label="Close Ask OG" onClick={closeAskOg}><X size={20} /></button></div>
            <SiteComposer projectId={projectId} embedded />
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

function MobileNavigation({ projectId, isActive, onAskOg, onMore }: Readonly<{ projectId: string; isActive: (suffix: string) => boolean; onAskOg: () => void; onMore: () => void }>) {
  return <nav className="mobile-bottom-nav" aria-label="Mobile project navigation"><Link className={isActive('') ? 'active' : ''} href={`/projects/${projectId}`}><Home size={20} /><span>Home</span></Link><Link className={isActive('/tasks') ? 'active' : ''} href={`/projects/${projectId}/tasks`}><ClipboardList size={20} /><span>Tasks</span></Link><button className="mobile-og-action" type="button" onClick={onAskOg}><span><Sparkles size={20} /></span><strong>OG</strong></button><Link className={isActive('/photos') ? 'active' : ''} href={`/projects/${projectId}/photos`}><Camera size={20} /><span>Photos</span></Link><button type="button" onClick={onMore}><Menu size={20} /><span>More</span></button></nav>;
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
