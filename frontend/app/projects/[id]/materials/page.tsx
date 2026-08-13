'use client';

import { ArrowRight, PackageOpen, Plus, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { useProject } from '@/components/project-context';
import { MaterialCreateDialog } from '@/components/material-create-dialog';
import { Pagination } from '@/components/pagination';
import { api, type Material } from '@/lib/api';

export default function MaterialsPage() {
  const { projectId, snapshot, refresh } = useProject();
  const searchParams = useSearchParams();
  const isSetup = searchParams?.get('setup') === '1';
  const materials = snapshot.materials;

  const [page, setPage] = useState(1);
  const pageSize = 15;
  const paginatedMaterials = useMemo(() => {
    return materials.slice((page - 1) * pageSize, page * pageSize);
  }, [materials, page, pageSize]);

  const [showCreate, setShowCreate] = useState(false);
  const [selectedMaterial, setSelectedMaterial] = useState<Material | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [delta, setDelta] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function closeModal() {
    setSelectedMaterial(null);
    setIsUpdating(false);
    setDelta('');
    setReason('');
    setError(null);
  }

  async function handleUpdateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedMaterial || !delta.trim() || !reason.trim()) return;

    const numericDelta = Number(delta);
    if (isNaN(numericDelta) || numericDelta === 0) {
      setError("Please enter a valid non-zero adjustment.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await api.adjustMaterialQuantity(
        projectId,
        selectedMaterial.id,
        numericDelta,
        selectedMaterial.unit,
        selectedMaterial.version,
        reason.trim()
      );
      await refresh();
      closeModal();
    } catch (err: any) {
      setError(err.message || 'Could not update quantity.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Materials</span>
          <h1>What you have. What&apos;s at risk.</h1>
          <p>Current stock, upcoming need and the requests waiting on you.</p>
        </div>
        <div className="page-heading-actions">
          <button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}>
            <Plus size={15} /> Add material
          </button>
          {isSetup && materials.length > 0 && (
            <Link href={`/projects/${projectId}?setup=1`} className="btn btn-accent btn-small">
              Finish setup <ArrowRight size={15} />
            </Link>
          )}
        </div>
      </div>

      {materials.length > 0 ? (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Material</th>
                <th>Available</th>
                <th className="action-cell"></th>
              </tr>
            </thead>
            <tbody>
              {paginatedMaterials.map((material) => (
                <tr key={material.id} onClick={() => setSelectedMaterial(material)} style={{ cursor: 'pointer' }}>
                  <td>
                    <span className={`status-pill ${material.status.toLowerCase()}`}>
                      {material.status === 'LOW' ? 'Running low' : material.status}
                    </span>
                  </td>
                  <td>
                    <div className="primary-cell">{material.name}</div>
                  </td>
                  <td>
                    <span className="numeric-cell">{material.quantity}</span> <span className="secondary-cell">{material.unit}</span>
                  </td>
                  <td className="action-cell">
                    <button className="btn btn-quiet btn-small">View details</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            currentPage={page}
            totalItems={materials.length}
            pageSize={pageSize}
            onPageChange={setPage}
          />
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-state-icon"><PackageOpen size={20} /></span>
          <h2>No materials tracked.</h2>
          <p>Add stock items to let OG monitor availability and requests.</p>
        </div>
      )}

      {showCreate && (
        <MaterialCreateDialog
          projectId={projectId}
          onClose={() => setShowCreate(false)}
          onRefresh={refresh}
        />
      )}

      {selectedMaterial && (
        <div className="modal-backdrop" role="presentation">
          <section className="create-project-modal material-create-modal" role="dialog" aria-modal="true">
            <button className="modal-close" onClick={closeModal} aria-label="Close">×</button>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <span className={`status-pill ${selectedMaterial.status.toLowerCase()}`}>
                {selectedMaterial.status === 'LOW' ? 'Running low' : selectedMaterial.status}
              </span>
            </div>

            <h2 style={{ fontSize: '1.45rem', marginBottom: '20px', letterSpacing: '-0.035em' }}>{selectedMaterial.name}</h2>

            {!isUpdating ? (
              <>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '20px' }}>
                  <strong style={{ fontSize: '3rem', fontFamily: "'Space Grotesk', sans-serif", letterSpacing: '-0.07em', lineHeight: 1 }}>{selectedMaterial.quantity}</strong>
                  <span style={{ color: 'var(--ink-soft)', fontSize: '0.8rem' }}>{selectedMaterial.unit} available</span>
                </div>

                <dl style={{ display: 'grid', gridTemplateColumns: '0.7fr 1.3fr', gap: '9px', padding: '14px 0', borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)' }}>
                  <div>
                    <dt style={{ color: 'var(--ink-faint)', fontSize: '0.66rem', fontWeight: 700, textTransform: 'uppercase' }}>Need</dt>
                    <dd style={{ margin: '4px 0 0', fontSize: '0.82rem', fontWeight: 700 }}>{selectedMaterial.need} {selectedMaterial.unit}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--ink-faint)', fontSize: '0.66rem', fontWeight: 700, textTransform: 'uppercase' }}>For Work</dt>
                    <dd style={{ margin: '4px 0 0', fontSize: '0.82rem', fontWeight: 700 }}>{selectedMaterial.forWork}</dd>
                  </div>
                </dl>

                <div style={{ marginTop: '20px', padding: '16px', background: 'var(--paper)', borderRadius: '12px' }}>
                  <strong style={{ fontSize: '0.8rem', color: 'var(--ink-faint)', textTransform: 'uppercase' }}>OG&apos;s Assessment</strong>
                  <p style={{ marginTop: '8px', color: 'var(--ink-soft)', fontSize: '0.88rem' }}>{selectedMaterial.note || 'No active notes on this material.'}</p>
                </div>

                <div style={{ marginTop: '30px' }}>
                  {selectedMaterial.status === 'LOW' ? (
                    <Link href={`/projects/${projectId}/approvals`} className="btn btn-primary btn-block">
                      Review stock request <ArrowRight size={14} />
                    </Link>
                  ) : (
                    <button type="button" onClick={() => setIsUpdating(true)} className="btn btn-primary btn-block">
                      Update quantities <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              </>
            ) : (
              <form onSubmit={handleUpdateSubmit} style={{ marginTop: '20px' }}>
                <p style={{ fontSize: '0.88rem', color: 'var(--ink-soft)', marginBottom: '20px' }}>
                  Current stock is <strong>{selectedMaterial.quantity} {selectedMaterial.unit}</strong>. Enter the adjustment below (e.g. 50 or -10).
                </p>
                <div className="form-group">
                  <label htmlFor="delta">Adjustment Amount</label>
                  <input
                    id="delta"
                    type="number"
                    className="form-input"
                    value={delta}
                    onChange={(e) => setDelta(e.target.value)}
                    required
                    disabled={submitting}
                    placeholder="e.g. 100 or -5"
                  />
                </div>
                <div className="form-group" style={{ marginTop: '16px' }}>
                  <label htmlFor="reason">Reason</label>
                  <input
                    id="reason"
                    type="text"
                    className="form-input"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    required
                    disabled={submitting}
                    placeholder="e.g. New delivery received"
                  />
                </div>

                {error && <div className="form-error" style={{ color: 'var(--orange-deep)', fontSize: '0.82rem', marginTop: '16px' }}>{error}</div>}

                <div style={{ display: 'flex', gap: '10px', marginTop: '24px' }}>
                  <button type="button" className="btn btn-quiet" onClick={() => setIsUpdating(false)} disabled={submitting}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={submitting}>
                    {submitting ? <><Loader2 size={15} className="spinner" /> Saving...</> : 'Save adjustment'}
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
