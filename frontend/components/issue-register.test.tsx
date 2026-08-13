// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IssueRegister } from './issue-register';

const issue = { id: 'iss_1', description: 'Electrician absent', type: 'BLOCKER' as const, severity: 'HIGH' as const, status: 'OPEN' as const, owner: 'usr_kofi', dueLabel: '8 Aug', taskIds: ['tsk_1'], evidenceRefs: ['sup_1'], location: null };
const task = { id: 'tsk_1', title: 'Electrical rough-in', status: 'BLOCKED' as const, assignee: 'usr_kofi', dueLabel: '8 Aug' };

describe('IssueRegister', () => {
  it('filters issues and exposes linked records in the drawer', () => {
    render(<IssueRegister issues={[issue]} tasks={[task]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Electrician absent' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Electrical rough-in');
    fireEvent.click(screen.getByRole('button', { name: 'Resolved' }));
    expect(screen.getByRole('heading', { name: 'No matching issues.' })).toBeVisible();
  });
});
