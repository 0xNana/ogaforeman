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
  ApiRequestError: class ApiRequestError extends Error {
    readonly status: number;
    readonly code: string;

    constructor(message: string, options: { status: number; code: string }) {
      super(message);
      this.status = options.status;
      this.code = options.code;
    }
  },
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
    window.sessionStorage.clear();
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

  it('announces an initial review load failure and offers a retry', async () => {
    getProjectImport.mockRejectedValueOnce(new Error('review service unavailable'));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('review service unavailable');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
  });

  it('uses the current import version and a stable decision key when confirming', async () => {
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    await screen.findByRole('heading', { name: 'Review project initialization' });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Initialize' }));

    await waitFor(() => expect(confirmProjectImport).toHaveBeenCalledWith('prj_ridge', 'imp_ridge', 3, expect.stringMatching(/^project-import-confirm:/)));
    expect(onFinished).toHaveBeenCalledWith('imported');
  });

  it('keeps an imported decision visible when refreshing the project view fails', async () => {
    onFinished.mockRejectedValueOnce(new Error('project snapshot unavailable'));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm & Initialize' }));

    expect(await screen.findByRole('heading', { name: 'Project initialized.' })).toBeVisible();
    expect(screen.getByRole('alert')).toHaveTextContent('project snapshot unavailable');
    expect(screen.getByRole('link', { name: 'Open project overview' })).toBeVisible();
  });

  it('blocks confirmation when the draft has conflicts and offers cancellation instead', async () => {
    getProjectImport.mockResolvedValue({ ...review, status: 'validation_failed', conflicts: [{ code: 'DEPENDENCY_CYCLE', message: 'Tasks create a dependency cycle.', entity_temp_id: null, existing_reference: null, source_reference: null }] });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: 'This draft has blocking conflicts.' })).toBeVisible();
    expect(await screen.findByText('Tasks create a dependency cycle.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Confirm & Initialize' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Import' }));
    await waitFor(() => expect(cancelProjectImport).toHaveBeenCalledWith('prj_ridge', 'imp_ridge', 3, expect.stringMatching(/^project-import-cancel:/)));
    expect(onFinished).toHaveBeenCalledWith('cancelled');
  });

  it.each([
    ['uploaded', 'Source uploaded.'],
    ['extracting', 'Extracting project plan.'],
    ['draft', 'Draft extracted.'],
    ['validating', 'Validating project plan.'],
    ['confirmed', 'Initialization confirmed.'],
    ['importing', 'Initializing project.'],
  ] as const)('renders the %s lifecycle state and can refresh it', async (status, title) => {
    getProjectImport.mockResolvedValue({ ...review, status });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: title })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Check status' }));
    await waitFor(() => expect(getProjectImport).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('button', { name: 'Confirm & Initialize' })).not.toBeInTheDocument();
  });

  it('shows an active-state refresh failure without discarding the durable status', async () => {
    getProjectImport
      .mockResolvedValueOnce({ ...review, status: 'extracting' })
      .mockRejectedValueOnce(new Error('status service unavailable'));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Check status' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('status service unavailable');
    expect(screen.getByRole('heading', { name: 'Extracting project plan.' })).toBeVisible();
  });

  it('renders extraction failure with a safe retry path back to setup', async () => {
    getProjectImport.mockResolvedValue({
      ...review,
      status: 'extraction_failed',
      project: null,
      tasks: [],
      dependencies: [],
      materials: [],
      requirements: [],
      failure_code: 'DEPENDENCY_UNAVAILABLE',
      failure_message: 'Project import extraction is temporarily unavailable.',
      retryable: true,
    });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: 'Extraction did not finish.' })).toBeVisible();
    expect(screen.getByText('Project import extraction is temporarily unavailable.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Return to setup' })).toHaveAttribute('href', '/projects/prj_ridge/setup?method=import');
    expect(screen.getByRole('button', { name: 'Cancel Import' })).toBeEnabled();
  });

  it('keeps extraction failure visible when cancellation cannot reach the API', async () => {
    getProjectImport.mockResolvedValue({ ...review, status: 'extraction_failed' });
    cancelProjectImport.mockRejectedValueOnce(new Error('decision service unavailable'));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel Import' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('decision service unavailable');
    expect(screen.getByRole('heading', { name: 'Extraction did not finish.' })).toBeVisible();
  });

  it('renders import failure with a retry that reuses the current draft version', async () => {
    getProjectImport.mockResolvedValue({
      ...review,
      status: 'import_failed',
      version: 7,
      failure_code: 'IMPORT_COMMIT_FAILED',
      failure_message: 'The project could not be initialized.',
      retryable: true,
    });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: 'Initialization did not finish.' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Retry initialization' }));
    await waitFor(() => expect(confirmProjectImport).toHaveBeenCalledWith('prj_ridge', 'imp_ridge', 7, expect.stringMatching(/^project-import-confirm:/)));
  });

  it.each([
    ['imported', 'Project initialized.', 'Open project overview', '/projects/prj_ridge'],
    ['cancelled', 'Import cancelled.', 'Return to setup', '/projects/prj_ridge/setup?method=import'],
  ] as const)('reconstructs the %s terminal state with its destination', async (status, title, linkName, href) => {
    getProjectImport.mockResolvedValue({ ...review, status });
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);

    expect(await screen.findByRole('heading', { name: title })).toBeVisible();
    expect(screen.getByRole('link', { name: linkName })).toHaveAttribute('href', href);
    expect(onFinished).not.toHaveBeenCalled();
  });

  it('suppresses rapid duplicate decisions before React rerenders', async () => {
    let finishConfirm: ((value: ProjectImportReviewRecord) => void) | undefined;
    confirmProjectImport.mockReturnValue(new Promise((resolve) => {
      finishConfirm = resolve;
    }));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    const button = await screen.findByRole('button', { name: 'Confirm & Initialize' });

    fireEvent.click(button);
    fireEvent.click(button);

    expect(confirmProjectImport).toHaveBeenCalledTimes(1);
    finishConfirm?.({ ...review, status: 'imported', version: 4 });
    await waitFor(() => expect(onFinished).toHaveBeenCalledWith('imported'));
  });

  it('reuses the same decision claim after a lost response and reload', async () => {
    confirmProjectImport.mockRejectedValueOnce(new Error('network lost'));
    const first = render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm & Initialize' }));
    await screen.findByRole('alert');
    const firstKey = confirmProjectImport.mock.calls[0]?.[3];
    first.unmount();

    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm & Initialize' }));

    await waitFor(() => expect(confirmProjectImport).toHaveBeenLastCalledWith('prj_ridge', 'imp_ridge', 3, firstKey));
  });

  it('reloads the current version after an optimistic version conflict', async () => {
    const { ApiRequestError } = await import('@/lib/api');
    getProjectImport
      .mockResolvedValueOnce(review)
      .mockResolvedValue({ ...review, version: 4 });
    confirmProjectImport.mockRejectedValueOnce(new ApiRequestError(
      'Project import changed; reload the review and try again.',
      { status: 409, code: 'PROJECT_IMPORT_VERSION_CONFLICT' },
    ));
    render(<ProjectImportReview projectId="prj_ridge" importId="imp_ridge" onFinished={onFinished} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm & Initialize' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('latest version');
    expect(getProjectImport).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Initialize' }));
    await waitFor(() => expect(confirmProjectImport).toHaveBeenLastCalledWith('prj_ridge', 'imp_ridge', 4, expect.any(String)));
  });
});
