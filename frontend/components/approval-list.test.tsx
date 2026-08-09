// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalList } from './approval-list';


describe('ApprovalList', () => {
  it('shows a persisted blocker follow-up in Needs you', () => {
    render(
      <ApprovalList
        approvals={[]}
        followUps={[{
          id: 'tsk_followup123',
          title: 'Follow up: Electrical rough-in',
          status: 'PENDING',
          assignee: 'usr_electrician123',
          dueLabel: 'Due 9 Aug',
          note: 'The assigned subcontractor was absent today.',
          needsAttention: true,
          sourceRefs: ['sup_update123', 'iss_blocker123', 'tsk_electrical123'],
        }]}
        projectId="prj_ridge"
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Follow up: Electrical rough-in' })).toBeVisible();
    expect(screen.getByText('Assigned to')).toBeVisible();
    expect(screen.getByText('usr_electrician123')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Open in Tasks' })).toHaveAttribute(
      'href',
      '/projects/prj_ridge/tasks',
    );
  });
});
