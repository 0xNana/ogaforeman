'use client';

import {
  Activity,
  Bell,
  ChevronDown,
  FileText,
  Home,
  ListTodo,
  LogOut,
  Menu,
  MessageSquareText,
  Package,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import type { Project } from '@/lib/api';
import { useAuth } from '@/src/lib/auth';

const navItems = [
  { label: 'Dashboard', suffix: '', icon: Home },
  { label: 'Site', suffix: '/site', icon: MessageSquareText },
  { label: 'Tasks', suffix: '/tasks', icon: ListTodo },
  { label: 'Materials', suffix: '/materials', icon: Package },
  { label: 'Reports', suffix: '/reports', icon: FileText },
  { label: 'Activity', suffix: '/activity', icon: Activity },
];

export function AppShell({ children, project }: Readonly<{ children: React.ReactNode; project: Project }>) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuth();
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [mobileOpen, setMobileOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  async function signOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await auth.signOutUser();
      router.replace('/sign-in');
    } catch (cause) {
      setSignOutError(cause instanceof Error ? cause.message : 'Oga could not sign you out. Try again.');
    } finally {
      setSigningOut(false);
    }
  }

  const isActive = (suffix: string) => suffix === ''
    ? pathname === `/projects/${projectId}`
    : pathname.startsWith(`/projects/${projectId}${suffix}`);

  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label="Project navigation">
        <Link className="logo-lockup" href="/" aria-label="Oga Foreman home">
          <span className="logo-mark" aria-hidden="true" />Oga Foreman
        </Link>
        <ProjectSwitcher project={project} />
        <nav className="app-nav" aria-label="Project sections">
          {navItems.map(({ label, suffix, icon: Icon }) => (
            <Link
              className={`app-nav-link${isActive(suffix) ? ' active' : ''}`}
              href={`/projects/${projectId}${suffix}`}
              key={label}
              aria-current={isActive(suffix) ? 'page' : undefined}
            >
              <Icon size={18} aria-hidden="true" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="app-sidebar-footer">
          <Link className="app-nav-link" href={`/projects/${projectId}/approvals`}>
            <div className="nav-icon-container">
              <Bell size={18} aria-hidden="true" />
              <span className="notification-badge pulse-ring">3</span>
            </div>
            <span>Needs you</span>
          </Link>
          <button className="app-nav-link app-nav-button" type="button" onClick={() => void signOut()} disabled={signingOut}>
            <LogOut size={18} aria-hidden="true" />
            <span>{signingOut ? 'Signing out…' : 'Sign Out'}</span>
          </button>
          {signOutError ? <p className="auth-error" role="alert">{signOutError}</p> : null}
          <p>Oga keeps watching unresolved work.</p>
        </div>
      </aside>

      <div className="app-main">
        <div className="app-topbar">
          <Link className="logo-lockup" href="/" aria-label="Oga Foreman home"><span className="logo-mark" aria-hidden="true" />Oga</Link>
          <button className="app-topbar-button" type="button" aria-label={mobileOpen ? 'Close project menu' : 'Open project menu'} aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)}>
            {mobileOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
        </div>
        {mobileOpen && (
          <div className="mobile-menu-overlay fade-in" onClick={() => setMobileOpen(false)}>
            <div className="mobile-project-menu slide-in-right glass-panel" onClick={(e) => e.stopPropagation()}>
              <div className="mobile-project-menu-inner">
                {navItems.map(({ label, suffix, icon: Icon }) => (
                  <Link className={`app-nav-link${isActive(suffix) ? ' active' : ''}`} href={`/projects/${projectId}${suffix}`} key={label} onClick={() => setMobileOpen(false)}>
                    <Icon size={18} aria-hidden="true" />{label}
                  </Link>
                ))}
                <Link className="app-nav-link" href={`/projects/${projectId}/approvals`} onClick={() => setMobileOpen(false)}>
                  <div className="nav-icon-container">
                    <Bell size={18} aria-hidden="true" />
                    <span className="notification-badge pulse-ring">3</span>
                  </div>
                  Needs you
                </Link>
                <button className="app-nav-link app-nav-button" type="button" onClick={() => void signOut()} disabled={signingOut}><LogOut size={18} aria-hidden="true" />{signingOut ? 'Signing out…' : 'Sign Out'}</button>
                {signOutError ? <p className="auth-error" role="alert">{signOutError}</p> : null}
              </div>
            </div>
          </div>
        )}
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

function ProjectSwitcher({ project }: Readonly<{ project: Project }>) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="project-switcher-container">
      <button className={`project-switcher ${isOpen ? 'active' : ''}`} type="button" aria-label="Current project" onClick={() => setIsOpen(!isOpen)}>
        <span className="avatar oga-avatar"><Home size={14} aria-hidden="true" /></span>
        <span className="project-switcher-copy"><strong>{project.name}</strong><span>{project.location}</span></span>
        <ChevronDown size={15} aria-hidden="true" className={`project-switcher-chevron ${isOpen ? 'open' : ''}`} />
      </button>
      {isOpen && (
        <div className="project-dropdown glass-panel fade-in-up">
          <div className="dropdown-header">Recent Projects</div>
          <Link href={`/projects/${project.id}`} className="dropdown-item active" onClick={() => setIsOpen(false)}>
            <div className="dropdown-item-content">
              <strong>{project.name}</strong>
              <span>{project.location}</span>
            </div>
          </Link>
          <button className="dropdown-action" onClick={() => setIsOpen(false)}>+ Create new project</button>
        </div>
      )}
    </div>
  );
}
