'use client';

import { ArrowRight, Loader2, PackageOpen, Plus, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { MaterialCreateDialog } from '@/components/material-create-dialog';
import { PageHeader } from '@/components/page-header';
import { useProject } from '@/components/project-context';
import { RecordDetails, RecordDrawer } from '@/components/record-drawer';
import { api, type Material, type MaterialRequest } from '@/lib/api';

export default function MaterialsPage() {
  const { projectId, snapshot, refresh } = useProject();
  const isSetup = useSearchParams()?.get('setup') === '1';
  const [tab, setTab] = useState<'INVENTORY' | 'REQUESTS'>('INVENTORY');
  const [query, setQuery] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<Material | null>(null);
  const [adjusting, setAdjusting] = useState(false);
  const [delta, setDelta] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const needle = query.trim().toLowerCase();
  const materials = useMemo(() => snapshot.materials.filter((item) => !needle || [item.id, item.name, item.forWork].some((value) => value.toLowerCase().includes(needle))), [needle, snapshot.materials]);
  const visibleRequests = useMemo(() => snapshot.materialRequests.filter((item) => !needle || [item.id, item.materialName, item.reason].some((value) => value.toLowerCase().includes(needle))), [needle, snapshot.materialRequests]);

  function closeDrawer() { setSelected(null); setAdjusting(false); setDelta(''); setReason(''); setError(null); }
  async function submitAdjustment(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const quantityDelta = Number(delta);
    if (!Number.isFinite(quantityDelta) || quantityDelta === 0 || !reason.trim()) { setError('Enter a non-zero adjustment and a reason.'); return; }
    setSubmitting(true); setError(null);
    try { await api.adjustMaterialQuantity(projectId, selected.id, quantityDelta, selected.unit, selected.version, reason.trim()); await refresh(); closeDrawer(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update quantity.'); }
    finally { setSubmitting(false); }
  }

  return <div><PageHeader eyebrow="Material control" title="Materials" description="Review inventory and follow each material request through its recorded lifecycle." actions={<><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} aria-hidden="true" /> Add material</button>{isSetup && snapshot.materials.length ? <Link href={`/projects/${projectId}?setup=1`} className="btn btn-accent btn-small">Finish setup <ArrowRight size={15} aria-hidden="true" /></Link> : null}</>} />
    <div className="register-toolbar"><label className="register-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Search materials</span><input type="search" placeholder="Search inventory or requests" value={query} onChange={(event) => setQuery(event.target.value)} /></label><div className="filter-tabs" aria-label="Material registers"><button className={`filter-tab${tab === 'INVENTORY' ? ' active' : ''}`} type="button" aria-pressed={tab === 'INVENTORY'} onClick={() => setTab('INVENTORY')}>Inventory</button><button className={`filter-tab${tab === 'REQUESTS' ? ' active' : ''}`} type="button" aria-pressed={tab === 'REQUESTS'} onClick={() => setTab('REQUESTS')}>Requests</button></div><span className="register-count">{tab === 'INVENTORY' ? materials.length : visibleRequests.length} records</span></div>
    {tab === 'INVENTORY' ? <InventoryTable materials={materials} onSelect={setSelected} /> : <RequestTable projectId={projectId} requests={visibleRequests} />}
    {showCreate ? <MaterialCreateDialog projectId={projectId} onClose={() => setShowCreate(false)} onRefresh={refresh} /> : null}
    {selected ? <RecordDrawer eyebrow={`Material · ${selected.id}`} title={selected.name} onClose={closeDrawer}><span className={`status-pill ${selected.status.toLowerCase()}`}>{materialStatus(selected.status)}</span>{adjusting ? <form className="drawer-form" onSubmit={submitAdjustment}><p>Current stock: <strong>{selected.quantity} {selected.unit}</strong></p><label>Adjustment amount<input type="number" step="any" value={delta} onChange={(event) => setDelta(event.target.value)} required disabled={submitting} /></label><label>Reason<input value={reason} onChange={(event) => setReason(event.target.value)} required disabled={submitting} /></label>{error ? <p role="alert" className="form-error">{error}</p> : null}<div><button className="btn btn-quiet" type="button" onClick={() => setAdjusting(false)} disabled={submitting}>Cancel</button><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? <><Loader2 size={15} className="spinner" /> Saving…</> : 'Save adjustment'}</button></div></form> : <><RecordDetails items={[{ label: 'On site', value: `${selected.quantity} ${selected.unit}` }, { label: 'Required', value: `${selected.need} ${selected.unit}` }, { label: 'Needed by', value: 'Not specified' }, { label: 'For work', value: selected.forWork }, { label: 'Assessment', value: selected.note }]} /><button className="btn btn-primary btn-block drawer-action" type="button" onClick={() => setAdjusting(true)}>Update quantities</button></>}</RecordDrawer> : null}
  </div>;
}

function InventoryTable({ materials, onSelect }: Readonly<{ materials: Material[]; onSelect: (material: Material) => void }>) {
  if (!materials.length) return <Empty title="No inventory records." text="Add stock items or change the search to see materials." />;
  return <div className="data-table-wrapper"><table className="data-table register-table"><thead><tr><th>Material</th><th>On site</th><th>Required</th><th>Unit</th><th>Needed by</th><th>Status</th></tr></thead><tbody>{materials.map((material) => <tr key={material.id}><th scope="row"><button className="register-row-link" type="button" onClick={() => onSelect(material)}>{material.name}</button></th><td>{material.quantity}</td><td>{material.need}</td><td>{material.unit}</td><td>Not specified</td><td><span className={`status-pill ${material.status.toLowerCase()}`}>{materialStatus(material.status)}</span></td></tr>)}</tbody></table></div>;
}

function RequestTable({ projectId, requests }: Readonly<{ projectId: string; requests: MaterialRequest[] }>) {
  if (!requests.length) return <Empty title="No material requests." text="Requests created from recorded shortages will appear here." />;
  return <div className="data-table-wrapper"><table className="data-table register-table"><thead><tr><th>Request</th><th>Material</th><th>Quantity</th><th>Reason</th><th>Needed by</th><th>Status</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td className="secondary-cell">{request.id}</td><th scope="row">{request.materialName}</th><td>{request.quantity} {request.unit}</td><td>{request.reason}</td><td>{request.neededBy}</td><td>{request.approvalId ? <Link href={`/projects/${projectId}/approvals`} className="register-status-link"><span className={`status-pill ${request.status.toLowerCase()}`}>{request.status.toLowerCase().replaceAll('_', ' ')}</span></Link> : <span className={`status-pill ${request.status.toLowerCase()}`}>{request.status.toLowerCase().replaceAll('_', ' ')}</span>}</td></tr>)}</tbody></table></div>;
}

function Empty({ title, text }: Readonly<{ title: string; text: string }>) { return <div className="empty-state"><span className="empty-state-icon"><PackageOpen size={20} aria-hidden="true" /></span><h2>{title}</h2><p>{text}</p></div>; }
function materialStatus(status: string) { return status === 'LOW' ? 'Running low' : status.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase()); }
