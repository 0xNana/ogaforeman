'use client';

import { ArrowRight, PackageOpen, Plus } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { useProject } from '@/components/project-context';
import { api } from '@/lib/api';

export default function MaterialsPage() {
  const { projectId, snapshot, refresh } = useProject();
  const materials = snapshot.materials;
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [unit, setUnit] = useState('bags');
  const [available, setAvailable] = useState('0');
  const [required, setRequired] = useState('0');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createMaterial(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createMaterial(projectId, {
        name: name.trim(),
        unit: unit.trim(),
        available_quantity: Number(available),
        minimum_required_quantity: Number(required),
      });
      await refresh();
      setName('');
      setAvailable('0');
      setRequired('0');
      setShowCreate(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The material could not be created.');
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Materials</span><h1>What you have. What&apos;s at risk.</h1><p>Current stock, upcoming need and the requests waiting on you.</p></div><div className="page-heading-actions"><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add material</button></div></div>
      {materials.length > 0 ? <div className="material-grid">{materials.map((material) => <article className="material-card" key={material.id}><div className="material-card-top"><span className={`status-pill ${material.status.toLowerCase()}`}>{material.status === 'LOW' ? 'Running low' : material.status}</span><span className="material-id">{material.id.replace('mat_', '').toUpperCase()}</span></div><h2>{material.name}</h2><div className="material-quantity"><strong>{material.quantity}</strong><span>{material.unit} reported</span></div><dl className="material-details"><div><dt>Need</dt><dd>{material.need} {material.unit}</dd></div><div><dt>For</dt><dd>{material.forWork}</dd></div></dl><p className="material-note"><strong>Oga:</strong> {material.note}</p>{material.status === 'LOW' ? <Link href={`/projects/${projectId}/approvals`} className="btn btn-primary btn-small btn-block">Review request <ArrowRight size={14} /></Link> : <Link href={`/projects/${projectId}/site?material=${material.id}`} className="activity-action">Update stock <ArrowRight size={13} /></Link>}</article>)}</div> : <div className="empty-state"><span className="empty-state-icon"><PackageOpen size={20} /></span><h2>Add the first project material.</h2><p>Oga matches reported stock to these canonical materials before changing quantities.</p><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}>Add material</button></div>}
      {showCreate ? <div className="modal-backdrop" role="presentation"><section className="create-project-modal" role="dialog" aria-modal="true" aria-labelledby="create-material-title"><button className="modal-close" type="button" onClick={() => setShowCreate(false)} aria-label="Close">×</button><span className="eyebrow">Project setup</span><h2 id="create-material-title">Add material stock Oga can track.</h2><form className="auth-form" onSubmit={createMaterial}><label>Material name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={300} placeholder="Cement" /></label><label>Unit<input value={unit} onChange={(event) => setUnit(event.target.value)} required maxLength={100} placeholder="bags" /></label><label>Available quantity<input type="number" min="0" step="any" value={available} onChange={(event) => setAvailable(event.target.value)} required /></label><label>Minimum required<input type="number" min="0" step="any" value={required} onChange={(event) => setRequired(event.target.value)} required /></label>{error ? <p role="alert">{error}</p> : null}<button className="btn btn-primary btn-block" type="submit" disabled={submitting}>{submitting ? 'Adding…' : 'Add material'}</button></form></section></div> : null}
    </div>
  );
}
