// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectImportSetup } from './project-import-setup';
import type { ProjectImportReviewRecord, ProjectImportSummary } from '@/lib/api';

const { createProjectImport, getLatestProjectImport, replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return {
    createProjectImport: vi.fn(),
    getLatestProjectImport: vi.fn(),
    replace,
    router: { replace },
  };
});

vi.mock('@/lib/api', () => ({
  api: { createProjectImport, getLatestProjectImport },
}));
vi.mock('next/navigation', () => ({ useRouter: () => router }));

const review = {
  id: 'imp_ridge',
  source_id: 'src_ridge',
  status: 'needs_review',
} as ProjectImportReviewRecord;

const failed: ProjectImportSummary = {
  id: 'imp_ridge',
  source_id: 'src_ridge',
  status: 'extraction_failed',
  version: 2,
  failure_code: 'dependency_unavailable',
  failure_message: 'Project import extraction is temporarily unavailable.',
  retryable: true,
  created_at: '2026-08-19T10:00:00Z',
  updated_at: '2026-08-19T10:01:00Z',
  phase_count: 0,
  task_count: 0,
  material_count: 0,
  requirement_count: 0,
};

describe('ProjectImportSetup', () => {
  beforeEach(() => {
    createProjectImport.mockReset();
    getLatestProjectImport.mockReset();
    replace.mockReset();
    window.sessionStorage.clear();
    getLatestProjectImport.mockResolvedValue(null);
    createProjectImport.mockResolvedValue(review);
  });

  afterEach(cleanup);

  it('starts extraction from pasted structured text and routes to its persisted import', async () => {
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);

    expect(await screen.findByRole('heading', { name: 'Add your project plan.' })).toBeVisible();
    fireEvent.change(screen.getByLabelText('Plan source'), {
      target: { value: '# Foundation\nTask: Excavation' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Extract project plan' }));

    await waitFor(() => expect(createProjectImport).toHaveBeenCalledWith(
      'prj_ridge',
      {
        source_name: 'pasted-project.md',
        source_text: '# Foundation\nTask: Excavation',
        source_type: 'markdown',
      },
      expect.stringMatching(/^project-import:/),
    ));
    expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/imports/imp_ridge');
  });

  it('rejects unsupported local files before import creation', async () => {
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);
    await screen.findByRole('heading', { name: 'Add your project plan.' });

    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [new File(['not supported'], 'plan.xer', { type: 'application/octet-stream' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Use a Word, Excel, PDF, CSV, text, or Markdown file');
    expect(screen.getByRole('heading', { name: 'Add your project plan.' })).toBeVisible();
    expect(createProjectImport).not.toHaveBeenCalled();
  });

  it.each([
    ['ridge-plan.txt', 'text'],
    ['ridge-plan.md', 'markdown'],
  ] as const)('reads supported local source %s as %s', async (fileName, sourceType) => {
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);
    await screen.findByRole('heading', { name: 'Add your project plan.' });
    const file = new File(['Task: Foundation'], fileName, { type: 'text/plain' });
    Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue('Task: Foundation') });

    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [file] },
    });
    await waitFor(() => expect(screen.getByLabelText('Plan source')).toHaveValue('Task: Foundation'));
    fireEvent.click(screen.getByRole('button', { name: 'Extract project plan' }));

    await waitFor(() => expect(createProjectImport).toHaveBeenCalledWith(
      'prj_ridge',
      expect.objectContaining({ source_name: fileName, source_type: sourceType }),
      expect.stringMatching(/^project-import:/),
    ));
  });

  it('rejects an oversized office file before import creation', async () => {
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);
    await screen.findByRole('heading', { name: 'Add your project plan.' });
    const file = new File([new Uint8Array([1])], 'ridge-plan.xlsx');
    Object.defineProperty(file, 'size', { value: 3_000_001 });

    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [file] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('larger than the 3 MB');
    expect(createProjectImport).not.toHaveBeenCalled();
  });

  it.each([
    ['ridge-plan.docx', 'file'],
    ['ridge-plan.pdf', 'file'],
    ['ridge-plan.xlsx', 'spreadsheet'],
    ['ridge-plan.xls', 'spreadsheet'],
    ['ridge-plan.csv', 'spreadsheet'],
  ] as const)('reads supported binary source %s as %s', async (fileName, sourceType) => {
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);
    await screen.findByRole('heading', { name: 'Add your project plan.' });
    const file = new File([new Uint8Array([1, 2, 3])], fileName);
    Object.defineProperty(file, 'arrayBuffer', {
      value: vi.fn().mockResolvedValue(Uint8Array.from([1, 2, 3]).buffer),
    });

    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [file] },
    });
    await waitFor(() => expect(screen.getByText(fileName)).toBeVisible());
    fireEvent.click(screen.getByRole('button', { name: 'Extract project plan' }));

    await waitFor(() => expect(createProjectImport).toHaveBeenCalledWith(
      'prj_ridge',
      {
        source_name: fileName,
        source_type: sourceType,
        source_data_base64: 'AQID',
      },
      expect.stringMatching(/^project-import:/),
    ));
  });

  it('restores the same claim and source after a failed request and reload', async () => {
    createProjectImport.mockRejectedValueOnce(new Error('network lost'));
    const first = render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);
    await screen.findByRole('heading', { name: 'Add your project plan.' });
    fireEvent.change(screen.getByLabelText('Plan source'), { target: { value: 'Task: Foundation' } });
    fireEvent.click(screen.getByRole('button', { name: 'Extract project plan' }));
    await screen.findByText(/couldn’t start extraction/i);
    const firstKey = createProjectImport.mock.calls[0]?.[2];
    first.unmount();

    getLatestProjectImport.mockResolvedValue(failed);
    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);

    expect(await screen.findByText('Extraction needs another try.')).toBeVisible();
    expect(screen.getByLabelText('Plan source')).toHaveValue('Task: Foundation');
    fireEvent.click(screen.getByRole('button', { name: 'Retry extraction' }));

    await waitFor(() => expect(createProjectImport).toHaveBeenLastCalledWith(
      'prj_ridge',
      expect.objectContaining({ source_text: 'Task: Foundation' }),
      firstKey,
    ));
  });

  it('recovers the latest nonterminal import without requiring its ID', async () => {
    getLatestProjectImport.mockResolvedValue({ ...failed, status: 'needs_review', retryable: false });

    render(<ProjectImportSetup projectId="prj_ridge" ownerKey="firebase-user" />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/imports/imp_ridge'));
    expect(createProjectImport).not.toHaveBeenCalled();
  });
});
