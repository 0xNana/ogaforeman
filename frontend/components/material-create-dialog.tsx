'use client';

import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, type CreateMaterialInput } from '@/lib/api';

const MAX_MATERIAL_ROWS = 20;

type MaterialDraft = {
  key: number;
  name: string;
  unit: string;
  available: string;
  required: string;
};

type MaterialCreateDialogProps = {
  projectId: string;
  onClose: () => void;
  onRefresh: () => Promise<void>;
};

function emptyMaterial(key: number): MaterialDraft {
  return { key, name: '', unit: 'bags', available: '0', required: '0' };
}

export function MaterialCreateDialog({ projectId, onClose, onRefresh }: Readonly<MaterialCreateDialogProps>) {
  const nextKey = useRef(2);
  const firstNameInput = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<MaterialDraft[]>([emptyMaterial(1)]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    firstNameInput.current?.focus();
  }, []);

  function updateRow(key: number, update: Partial<MaterialDraft>) {
    setRows((current) => current.map((row) => (
      row.key === key ? { ...row, ...update } : row
    )));
  }

  function addRow() {
    setRows((current) => [...current, emptyMaterial(nextKey.current++)]);
  }

  function removeRow(key: number) {
    setRows((current) => current.filter((row) => row.key !== key));
  }

  async function createMaterials(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const createdKeys: number[] = [];

    try {
      for (const row of rows) {
        const input: CreateMaterialInput = {
          name: row.name.trim(),
          unit: row.unit.trim(),
          available_quantity: Number(row.available),
          minimum_required_quantity: Number(row.required),
        };
        await api.createMaterial(projectId, input);
        createdKeys.push(row.key);
      }
      await onRefresh();
      onClose();
    } catch (cause) {
      if (createdKeys.length > 0) {
        setRows((current) => current.filter((row) => !createdKeys.includes(row.key)));
        await onRefresh();
      }
      const message = cause instanceof Error
        ? cause.message
        : 'The materials could not be created.';
      setError(createdKeys.length > 0
        ? `${createdKeys.length} material${createdKeys.length === 1 ? '' : 's'} added. ${message}`
        : message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="create-project-modal material-create-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-material-title"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !submitting) onClose();
        }}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Close" disabled={submitting}>
          ×
        </button>
        <span className="eyebrow">Project setup</span>
        <h2 id="create-material-title">Add materials Oga can track.</h2>
        <p className="material-create-intro">
          Add up to {MAX_MATERIAL_ROWS} stock items, then save them together.
        </p>
        <form className="auth-form material-create-form" onSubmit={createMaterials}>
          <div className="material-entry-list">
            {rows.map((row, index) => {
              const position = index + 1;
              return (
                <fieldset className="material-entry" key={row.key} disabled={submitting}>
                  <legend className="sr-only">Material {position}</legend>
                  <div className="material-entry-heading">
                    <span className="material-entry-title" aria-hidden="true">Material {position}</span>
                    {rows.length > 1 ? (
                      <button
                        className="material-remove-button"
                        type="button"
                        onClick={() => removeRow(row.key)}
                        aria-label={`Remove material ${position}`}
                      >
                        <Trash2 size={14} aria-hidden="true" /> Remove
                      </button>
                    ) : null}
                  </div>
                  <div className="material-entry-grid">
                    <label>
                      Material name
                      <input
                        ref={index === 0 ? firstNameInput : undefined}
                        aria-label={`Material name ${position}`}
                        value={row.name}
                        onChange={(event) => updateRow(row.key, { name: event.target.value })}
                        required
                        maxLength={300}
                        placeholder="Cement"
                      />
                    </label>
                    <label>
                      Unit
                      <input
                        aria-label={`Unit ${position}`}
                        value={row.unit}
                        onChange={(event) => updateRow(row.key, { unit: event.target.value })}
                        required
                        maxLength={100}
                        placeholder="bags"
                      />
                    </label>
                    <label>
                      Available quantity
                      <input
                        aria-label={`Available quantity ${position}`}
                        type="number"
                        min="0"
                        step="any"
                        value={row.available}
                        onChange={(event) => updateRow(row.key, { available: event.target.value })}
                        required
                      />
                    </label>
                    <label>
                      Minimum required
                      <input
                        aria-label={`Minimum required ${position}`}
                        type="number"
                        min="0"
                        step="any"
                        value={row.required}
                        onChange={(event) => updateRow(row.key, { required: event.target.value })}
                        required
                      />
                    </label>
                  </div>
                </fieldset>
              );
            })}
          </div>
          {rows.length < MAX_MATERIAL_ROWS ? (
            <button
              className="btn btn-quiet btn-small material-add-row"
              type="button"
              onClick={addRow}
              disabled={submitting}
            >
              <Plus size={15} aria-hidden="true" /> Add another material
            </button>
          ) : null}
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
            {submitting
              ? `Adding ${rows.length} material${rows.length === 1 ? '' : 's'}…`
              : `Add ${rows.length} material${rows.length === 1 ? '' : 's'}`}
          </button>
        </form>
      </section>
    </div>
  );
}
