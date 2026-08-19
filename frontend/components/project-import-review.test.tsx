// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectImportReview } from './project-import-review';
import type { ProjectImportReviewRecord } from '@/lib/api';

const { cancelProjectImport, confirmProjectImport, getProjectImport, onFinished } = vi.hoisted(() => ({
  cancelProjectImport: vi.fn(),
  confirmProjectImport: vi.fn(),
  getProjectImport: vi.fn(),
  onFinished: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: { cancelProjectImport, confirmProjectImport, getProjectImport },
}));

const review: ProjectImportReviewRecord = {
  id: 'imp_ridge',
  source_id: 'src_ridge',
  status: 'needs_review',
  version: 3,
  project: { name: 'Ridge House', description: null, type: 'Residential', location: 'East Legon', start_date: '2026-09-01', target_end_date: null, status: 'PLANNING' },
  phases: [],
  tasks: [{ temp_id: 'tmp_task_blockwork', name: 'First-floor blockwork', description: null, phase_temp_id: null, planned_start: '2026-09-01', planned_finish: '2026-09-04', actual_completion: null, duration: '4', initial_status: 'planned', location: 'First floor', trade: 'Masonry', assignee_reference: null, source_reference: null }],
  dependencies: [{ predecessor_temp_id: 'tmp_task_blockwork', successor_temp_id: 'tmp_task_plastering', type: 'finish_to_start', source_reference: null }],
  materials: [{ temp_id: 'tmp_material_cement', name: 'Cement', canonical_unit: 'bags', initial_on_hand_quantity: '10', location: 'Store', source_reference: null }],
  requirements: [{ task_temp_id: 'tmp_task_blockwork', material_temp_id: 'tmp_material_cement', required_quantity: '40', unit: 'bags', required_by: '2026-09-04', source_reference: null, confidence: '1' }],
  milestones: [],
  warnings: [{ code: 'UNRESOLVED_ASSIGNEE', message: 'Masonry team could not be matched.', field: 'assignee_reference', source_reference: null }],
  conflicts: [],
  unresolved_references: [],
  failure_code: null,
  failure_message: null,
  retryable: false,
  created_at: '2026-08-19T10:00:00Z',
  updated_at: '2026-08-19T10:01:00Z',
  phase_count: 0,
  task_count: 1,
  material_count: 1,
  requirement_count: 1,
  replayed: false,
};

describe('ProjectImportReview', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    getProjectImport.mockResolvedValue(review);
    cancelProjectImport.mockResolvedValue({ ...review, status: 'cancelled', version: 4 });
    confirmProjectImport.mockResolvedValue({ ...review, status: 'imported', version: 4 });
  });

  it('shows a compact, read-only accounting of the proposed canonical records', async () => {
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: 'Review project initialization' })).toBeVisible();
    expect(screen.getByLabelText('1 Task')).toBeVisible();
    expect(screen.getByLabelText('1 Dependency')).toBeVisible();
    expect(screen.getByLabelText('1 Material')).toBeVisible();
    expect(screen.getByLabelText('1 Requirement')).toBeVisible();
    expect(screen.getByLabelText('1 Warning')).toBeVisible();
    expect(screen.getByRole('row', { name: /First-floor blockwork/ })).toHaveTextContent('Masonry');
    expect(screen.getAllByText('First-floor blockwork').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('tmp_task_plastering')).toBeVisible();
    expect(screen.getByRole('row', { name: /Cement/ })).toHaveTextContent('10');
    expect(screen.getByRole('heading', { name: 'First-floor blockwork' })).toBeVisible();
    expect(screen.getByText('Masonry team could not be matched.')).toBeVisible();
  });

  it('uses the current import version and a stable decision key when confirming', async () => {
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    await screen.findByRole('heading', { name: 'Review project initialization' });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Initialize' }));

    await waitFor(() => expect(confirmProjectImport).toHaveBeenCalledWith('prj_ridge', 'imp_ridge', 3, expect.stringMatching(/^project-import-confirm:/)));
    expect(onFinished).toHaveBeenCalledWith('imported');
  });

  it('blocks confirmation when the draft has conflicts and offers cancellation instead', async () => {
    getProjectImport.mockResolvedValue({ ...review, conflicts: [{ code: 'DEPENDENCY_CYCLE', message: 'Tasks create a dependency cycle.', entity_temp_id: null, existing_reference: null, source_reference: null }] });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByText('Tasks create a dependency cycle.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Confirm & Initialize' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Import' }));
    await waitFor(() => expect(cancelProjectImport).toHaveBeenCalledWith('prj_ridge', 'imp_ridge', 3, expect.stringMatching(/^project-import-cancel:/)));
    expect(onFinished).toHaveBeenCalledWith('cancelled');
  });
});
