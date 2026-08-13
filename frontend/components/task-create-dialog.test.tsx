// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '@/lib/api';
import { TaskCreateDialog } from './task-create-dialog';

vi.mock('@/lib/api', () => ({ api: { createTask: vi.fn() } }));
vi.mock('@/components/project-context', () => ({
  useProject: () => ({
    snapshot: { members: [{ id: 'usr_kofi', displayName: 'Kofi Foreman' }] },
  }),
}));

describe('TaskCreateDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('submits operational task fields and member assignment', async () => {
    vi.mocked(api.createTask).mockResolvedValue({} as never);
    render(<TaskCreateDialog projectId="prj_ridge" onClose={vi.fn()} onRefresh={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Task name 1'), { target: { value: 'Electrical first fix' } });
    fireEvent.change(screen.getByLabelText('Trade'), { target: { value: 'Electrical' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'First floor' } });
    fireEvent.change(screen.getByLabelText('Assignee'), { target: { value: 'usr_kofi' } });
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-08-14' } });
    fireEvent.change(screen.getByLabelText('Finish'), { target: { value: '2026-08-16' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 task' }));

    await waitFor(() => expect(api.createTask).toHaveBeenCalledWith('prj_ridge', {
      title: 'Electrical first fix',
      trade: 'Electrical',
      location: 'First floor',
      assigned_to: 'usr_kofi',
      planned_start: '2026-08-14T00:00:00Z',
      planned_end: '2026-08-16T23:59:59Z',
    }));
  });
});
