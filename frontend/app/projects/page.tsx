'use client';

import { ArrowRight, FolderPlus, MapPin } from 'lucide-react';
import Link from 'next/link';
import { FormEvent, useEffect, useState } from 'react';
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

  useEffect(() => {
    if (auth.state !== 'authenticated') return;
    api.listProjects()
      .then(setProjects)
      .catch(() => setError('We could not load your projects.'))
      .finally(() => setLoading(false));
  }, [auth.state]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    try {
      const project = await api.createProject({
        name: name.trim(),
        location: location.trim(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Africa/Accra',
      });
      router.push(`/projects/${project.id}`);
    } catch {
      setError('We could not create that project. Check the details and try again.');
    }
  }

  if (auth.state === 'loading') return <div className="auth-page"><div className="loading-stack" aria-busy="true"><div className="loading-block loading-heading" /></div></div>;
  if (auth.state !== 'authenticated') return <div className="empty-state"><h1>Sign in to see your projects.</h1><Link className="btn btn-primary" href="/sign-in">Sign in <ArrowRight size={16} /></Link></div>;

  return <main className="projects-page"><div className="container projects-inner"><header className="projects-header"><div><span className="eyebrow">Your sites</span><h1>Keep the work moving.</h1><p>Open a project or start with the next one.</p></div><button className="btn btn-accent" type="button" onClick={() => setShowCreate(true)}><FolderPlus size={17} /> New project</button></header>
    {error ? <p className="auth-error" role="alert">{error}</p> : null}
    {loading ? <div className="loading-stack" aria-busy="true"><div className="loading-block loading-card" /></div> : projects.length > 0 ? <div className="project-list">{projects.map((project) => <Link className="project-list-card" href={`/projects/${project.id}`} key={project.id}><span className="project-list-icon"><MapPin size={18} /></span><span><strong>{project.name}</strong><small>{project.location}</small></span><ArrowRight size={17} /></Link>)}</div> : <div className="empty-state projects-empty"><span className="empty-state-icon"><FolderPlus size={20} /></span><h2>Nothing here yet.</h2><p>Create your first project and tell Oga what happened on site.</p><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}>Create a project</button></div>}
    {showCreate ? <div className="modal-backdrop" role="presentation"><section className="create-project-modal" role="dialog" aria-modal="true" aria-labelledby="create-project-title"><button className="modal-close" type="button" onClick={() => setShowCreate(false)} aria-label="Close">×</button><span className="eyebrow">New project</span><h2 id="create-project-title">Give this site a name.</h2><form className="auth-form" onSubmit={createProject}><label>Project name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} placeholder="Ridge House" /></label><label>Location<input value={location} onChange={(event) => setLocation(event.target.value)} required maxLength={500} placeholder="East Legon, Accra" /></label><button className="btn btn-primary btn-block" type="submit">Create project <ArrowRight size={16} /></button></form></section></div> : null}
  </div></main>;
}
