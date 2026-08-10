'use client';

import { ArrowRight, PackageOpen, Plus } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { useProject } from '@/components/project-context';
import { MaterialCreateDialog } from '@/components/material-create-dialog';

export default function MaterialsPage() {
  const { projectId, snapshot, refresh } = useProject();
  const materials = snapshot.materials;
  const [showCreate, setShowCreate] = useState(false);
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Materials</span><h1>What you have. What&apos;s at risk.</h1><p>Current stock, upcoming need and the requests waiting on you.</p></div><div className="page-heading-actions"><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add material</button></div></div>
      {materials.length > 0 ? <div className="material-grid">{materials.map((material) => <article className="material-card" key={material.id}><div className="material-card-top"><span className={`status-pill ${material.status.toLowerCase()}`}>{material.status === 'LOW' ? 'Running low' : material.status}</span><span className="material-id">{material.id.replace('mat_', '').toUpperCase()}</span></div><h2>{material.name}</h2><div className="material-quantity"><strong>{material.quantity}</strong><span>{material.unit} reported</span></div><dl className="material-details"><div><dt>Need</dt><dd>{material.need} {material.unit}</dd></div><div><dt>For</dt><dd>{material.forWork}</dd></div></dl><p className="material-note"><strong>Oga:</strong> {material.note}</p>{material.status === 'LOW' ? <Link href={`/projects/${projectId}/approvals`} className="btn btn-primary btn-small btn-block">Review request <ArrowRight size={14} /></Link> : <Link href={`/projects/${projectId}/site?material=${material.id}`} className="activity-action">Update stock <ArrowRight size={13} /></Link>}</article>)}</div> : <div className="empty-state"><span className="empty-state-icon"><PackageOpen size={20} /></span><h2>Add the first project material.</h2><p>Oga matches reported stock to these canonical materials before changing quantities.</p><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}>Add material</button></div>}
      {showCreate ? (
        <MaterialCreateDialog
          projectId={projectId}
          onClose={() => setShowCreate(false)}
          onRefresh={refresh}
        />
      ) : null}
    </div>
  );
}
