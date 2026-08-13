// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { IssueRegister } from './issue-register';

const issue = { id: 'iss_1', description: 'Electrician absent', type: 'BLOCKER' as const, severity: 'HIGH' as const, status: 'OPEN' as const, owner: 'Kofi Foreman', dueLabel: '8 Aug', taskIds: ['tsk_1'], evidenceRefs: ['sup_1'], location: 'First floor' };
const task = { id: 'tsk_1', title: 'Electrical rough-in', status: 'BLOCKED' as const, assignee: 'Kofi Foreman', dueLabel: '8 Aug' };

afterEach(cleanup);

describe('IssueRegister', () => {
  it('distinguishes a clear site from filtered results', () => {
    render(<IssueRegister issues={[]} tasks={[]} />);
    expect(screen.getByRole('heading', { name: 'Nothing blocking the site.' })).toBeVisible();
    expect(screen.getByText('OG is watching for changes.')).toBeVisible();
  });

  it('filters issues and exposes linked records in the drawer', () => {
    render(<IssueRegister issues={[issue]} tasks={[task]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Electrician absent' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Electrical rough-in');
    expect(screen.getByRole('dialog')).toHaveTextContent('First floor');
    expect(screen.queryByText('iss_1')).not.toBeInTheDocument();
    expect(screen.queryByText('sup_1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Resolved' }));
    expect(screen.getByRole('heading', { name: 'No matching issues.' })).toBeVisible();
  });
});
