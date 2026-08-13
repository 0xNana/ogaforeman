// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TaskBoard } from './task-board';

vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams() }));

const tasks = [
  { id: 'tsk_mine', title: 'Electrical rough-in', status: 'BLOCKED' as const, assignee: 'usr_me', dueLabel: 'Due today', startLabel: '8 Aug', progress: 20, dependencyIds: ['tsk_done'], blocking: 'Ceiling work', sourceRefs: ['iss_blocker', 'sup_update'] },
  { id: 'tsk_done', title: 'Blockwork', status: 'COMPLETED' as const, assignee: 'usr_other', dueLabel: 'Completed 7 Aug', progress: 100 },
];

describe('TaskBoard', () => {
  it('searches and filters the operational register', () => {
    render(<TaskBoard projectId="prj_ridge" tasks={tasks} viewerId="usr_me" onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'My work' }));
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toBeVisible();
    expect(screen.queryByRole('row', { name: /Blockwork/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search tasks' }), { target: { value: 'missing' } });
    expect(screen.getByRole('heading', { name: 'No matching tasks.' })).toBeVisible();
  });

  it('opens a task detail drawer with recorded and unavailable fields', () => {
    render(<TaskBoard projectId="prj_ridge" tasks={tasks} viewerId="usr_me" onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Electrical rough-in' }));
    expect(screen.getByRole('dialog', { name: 'Electrical rough-in' })).toHaveTextContent('Blockwork');
    expect(screen.getByRole('dialog', { name: 'Electrical rough-in' })).toHaveTextContent('Not available in this projection');
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
