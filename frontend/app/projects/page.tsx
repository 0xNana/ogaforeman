'use client';

import { AlertTriangle, ArrowRight, FolderPlus, MapPin, FileText } from 'lucide-react';
import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, type Project } from '@/lib/api';
import { useAuth } from '@/src/lib/auth';

export default function ProjectsPage() {
  const auth = useAuth();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [error, setError] = useState('');

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setProjects(await api.listProjects());
    } catch {
      setError('We could not load your projects.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.state !== 'authenticated') return;
    queueMicrotask(() => void loadProjects());
  }, [auth.state, loadProjects]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    try {
      const project = await api.createProject({
        name: name.trim(),
        location: location.trim(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Africa/Accra',
      });
      router.push(`/projects/${project.id}?setup=1`);
    } catch {
      setError('We could not create that project. Check the details and try again.');
    }
  }

  if (auth.state === 'loading') return <div className="auth-page"><div className="loading-stack" aria-busy="true"><div className="loading-block loading-heading" /></div></div>;
  if (auth.state !== 'authenticated') return <div className="empty-state"><h1>Sign in to see your projects.</h1><Link className="btn btn-primary" href="/sign-in">Sign in <ArrowRight size={16} /></Link></div>;

  return <main className="projects-page"><div className="container projects-inner">{(loading || error || projects.length > 0) && <header className="projects-header"><div><span className="eyebrow">Your sites</span><h1>Keep the work moving.</h1><p>Open a project or start with the next one.</p></div>{error ? <button className="btn btn-quiet" type="button" onClick={() => void loadProjects()}>Try again</button> : <button className="btn btn-accent" type="button" onClick={() => setShowCreate(true)}><FolderPlus size={17} /> New project</button>}</header>}
    {loading ? <div className="loading-stack" aria-busy="true"><div className="loading-block loading-card" /></div> : error ? <div className="empty-state projects-empty" role="alert"><span className="empty-state-icon"><AlertTriangle size={20} /></span><h2>We could not load your projects.</h2><p>Check your connection, then try again.</p></div> : projects.length > 0 ? <div className="project-list">{projects.map((project) => <Link className="project-list-card" href={`/projects/${project.id}`} key={project.id}><span className="project-list-icon"><MapPin size={18} /></span><span><strong>{project.name}</strong><small>{project.location}</small></span><ArrowRight size={17} /></Link>)}</div> : <div className="onboarding-panel"><div className="onboarding-intro"><span className="eyebrow">Welcome to OG</span><h2>Your AI Site Coordinator.</h2><p>OG turns messy site updates into verified progress, tracks your materials, and keeps your team unblocked. Create your first project to get started.</p><button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>Create your first project <ArrowRight size={16} /></button></div><div className="onboarding-features"><div className="onboarding-feature"><span className="onboarding-feature-icon"><MapPin size={20} /></span><h3>Progress tracking</h3><p>Turn raw updates into structured task completion metrics automatically.</p></div><div className="onboarding-feature"><span className="onboarding-feature-icon"><AlertTriangle size={20} /></span><h3>Blocker resolution</h3><p>Automatically detect risks and route them for quick approval.</p></div><div className="onboarding-feature"><span className="onboarding-feature-icon"><FolderPlus size={20} /></span><h3>Material ledgers</h3><p>Maintain an accurate, real-time record of stock and inbound requests.</p></div><div className="onboarding-feature"><span className="onboarding-feature-icon"><FileText size={20} /></span><h3>Daily reports</h3><p>Generate comprehensive site briefings without writing a single word.</p></div></div></div>}
    {showCreate ? <div className="modal-backdrop" role="presentation"><section className="create-project-modal" role="dialog" aria-modal="true" aria-labelledby="create-project-title"><button className="modal-close" type="button" onClick={() => setShowCreate(false)} aria-label="Close">×</button><span className="eyebrow">New project</span><h2 id="create-project-title">Give this site a name.</h2><form className="auth-form" onSubmit={createProject}><label>Project name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} placeholder="Ridge House" /></label><label>Location<input value={location} onChange={(event) => setLocation(event.target.value)} required maxLength={500} placeholder="East Legon, Accra" /></label><button className="btn btn-primary btn-block" type="submit">Create project <ArrowRight size={16} /></button></form></section></div> : null}
  </div></main>;
}
