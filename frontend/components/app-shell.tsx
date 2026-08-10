'use client';

import {
  Activity,
  Bell,
  ChevronDown,
  FileText,
  Home,
  ListTodo,
  Menu,
  MessageSquareText,
  Package,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, usePathname } from 'next/navigation';
import { useState } from 'react';
import type { Project } from '@/lib/api';

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
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [mobileOpen, setMobileOpen] = useState(false);

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
            <Bell size={18} aria-hidden="true" />
            <span>Needs you</span>
          </Link>
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
          <div className="mobile-project-menu">
            <div className="mobile-project-menu-inner">
              {navItems.map(({ label, suffix, icon: Icon }) => (
                <Link className={`app-nav-link${isActive(suffix) ? ' active' : ''}`} href={`/projects/${projectId}${suffix}`} key={label} onClick={() => setMobileOpen(false)}>
                  <Icon size={18} aria-hidden="true" />{label}
                </Link>
              ))}
              <Link className="app-nav-link" href={`/projects/${projectId}/approvals`} onClick={() => setMobileOpen(false)}><Bell size={18} aria-hidden="true" />Needs you</Link>
            </div>
          </div>
        )}
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

function ProjectSwitcher({ project }: Readonly<{ project: Project }>) {
  return (
    <button className="project-switcher" type="button" aria-label="Current project">
      <span className="avatar oga-avatar"><Home size={14} aria-hidden="true" /></span>
      <span className="project-switcher-copy"><strong>{project.name}</strong><span>{project.location}</span></span>
      <ChevronDown size={15} aria-hidden="true" />
    </button>
  );
}
