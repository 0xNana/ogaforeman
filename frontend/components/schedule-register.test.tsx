// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScheduleRegister } from './schedule-register';

const tasks = [
  { id: 'tsk_electrical', title: 'Electrical rough-in', status: 'BLOCKED' as const, assignee: 'Kofi', dueLabel: 'Due 15 Aug', startLabel: '13 Aug', startDate: '2026-08-13', finishDate: '2026-08-15', durationDays: 3, progress: 20, dependencyIds: [], downstreamIds: ['tsk_ceiling'], atRisk: false, sourceRefs: ['sup_morning'] },
  { id: 'tsk_ceiling', title: 'Ceiling installation', status: 'PENDING' as const, assignee: 'Ama', dueLabel: 'Due 18 Aug', startLabel: '16 Aug', startDate: '2026-08-16', finishDate: '2026-08-18', durationDays: 3, progress: 0, dependencyIds: ['tsk_electrical'], downstreamIds: [], atRisk: true },
  { id: 'tsk_handover', title: 'Handover milestone', status: 'PENDING' as const, assignee: 'Ama', dueLabel: 'Due 20 Aug', startLabel: '20 Aug', startDate: '2026-08-20', finishDate: '2026-08-20', durationDays: 1, progress: 0, dependencyIds: [], downstreamIds: [], isMilestone: true, atRisk: false },
];

describe('ScheduleRegister', () => {
  it('filters schedule risk and switches between list and Gantt', () => {
    render(<ScheduleRegister tasks={tasks} />);
    fireEvent.click(screen.getByRole('button', { name: 'At risk' }));
    expect(screen.getByRole('row', { name: /Ceiling installation/ })).toBeVisible();
    expect(screen.queryByRole('row', { name: /Electrical rough-in/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Gantt' }));
    expect(screen.getByLabelText('Schedule timeline')).toHaveTextContent('Ceiling installation');
  });

  it('shows dependencies and downstream impact in the activity drawer', () => {
    render(<ScheduleRegister tasks={tasks} />);
    fireEvent.click(screen.getByRole('button', { name: 'Electrical rough-in' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Ceiling installation');
    expect(screen.getByRole('dialog')).toHaveTextContent('sup_morning');
  });
});
