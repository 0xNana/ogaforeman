// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { TaskBoard } from './task-board';

vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams() }));
afterEach(cleanup);

const tasks = [
  { id: 'tsk_mine', title: 'Electrical rough-in', status: 'BLOCKED' as const, assignee: 'Kofi Foreman', assigneeId: 'usr_me', location: 'First floor', trade: 'Electrical', dueLabel: 'Due today', startLabel: '8 Aug', progress: 20, dependencyIds: ['tsk_done'], blocking: 'Ceiling work', sourceRefs: ['iss_blocker', 'sup_update'] },
  { id: 'tsk_done', title: 'Blockwork', status: 'COMPLETED' as const, assignee: 'usr_other', dueLabel: 'Completed 7 Aug', progress: 100 },
];

describe('TaskBoard', () => {
  it('searches and filters the operational register', () => {
    render(<TaskBoard projectId="prj_ridge" tasks={tasks} viewerId="usr_me" onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'My work' }));
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toBeVisible();
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toHaveTextContent('First floor');
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toHaveTextContent('Electrical');
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toHaveTextContent('Kofi Foreman');
    expect(screen.queryByRole('row', { name: /Blockwork/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search tasks' }), { target: { value: 'missing' } });
    expect(screen.getByRole('heading', { name: 'No matching tasks.' })).toBeVisible();
  });

  it('opens a task detail drawer with recorded and unavailable fields', () => {
    render(<TaskBoard projectId="prj_ridge" tasks={tasks} viewerId="usr_me" onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Electrical rough-in' }));
    expect(screen.getByRole('dialog', { name: 'Electrical rough-in' })).toHaveTextContent('Blockwork');
    expect(screen.getByRole('dialog', { name: 'Electrical rough-in' })).toHaveTextContent('Not available in this projection');
    expect(screen.queryByText('tsk_mine')).not.toBeInTheDocument();
    expect(screen.queryByText('iss_blocker')).not.toBeInTheDocument();
    expect(screen.queryByText('sup_update')).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not expose internal task identifiers in the register', () => {
    render(<TaskBoard projectId="prj_ridge" tasks={tasks} viewerId="usr_me" onRefresh={vi.fn()} />);

    expect(screen.queryByRole('columnheader', { name: 'ID' })).not.toBeInTheDocument();
    expect(screen.queryByText('tsk_mine')).not.toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Search tasks' })).toHaveAttribute(
      'placeholder',
      'Search tasks or assignees',
    );
  });
});
