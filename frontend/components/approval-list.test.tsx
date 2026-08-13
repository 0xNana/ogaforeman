// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApprovalList } from './approval-list';
import { ApiRequestError, api, type Approval } from '@/lib/api';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const pendingApproval: Approval = {
  id: 'apr_cement123', type: 'Material request', title: 'Cement', status: 'PENDING',
  quantity: '90 bags', neededFor: 'Ground-floor plastering', neededBy: 'Tomorrow',
  reason: '10 bags were reported on site against a requirement of 100.',
  requestedBy: 'OG', date: '13 Aug, 10:17', resolvedBy: null, resolvedAt: null, version: 0,
};

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

  it('explains a consequential request and records who approved it and when', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(api, 'resolveApproval').mockResolvedValue({
      ...pendingApproval, status: 'APPROVED', resolvedBy: 'usr_ace123', resolvedAt: '13 Aug, 10:18', version: 1,
    });
    render(<ApprovalList approvals={[pendingApproval]} followUps={[]} projectId="prj_ridge" onRefresh={onRefresh} />);

    const card = screen.getByRole('article');
    expect(within(card).getByText('90 bags')).toBeVisible();
    expect(within(card).getByText('Ground-floor plastering')).toBeVisible();
    expect(within(card).getByRole('heading', { name: 'Why OG prepared this' })).toBeVisible();

    fireEvent.click(within(card).getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(within(card).getByRole('status')).toHaveTextContent('APPROVED'));
    expect(within(card).getByText('by usr_ace123 · 13 Aug, 10:18')).toBeVisible();
    expect(api.resolveApproval).toHaveBeenCalledWith('prj_ridge', 'apr_cement123', 'APPROVE', 0);
  });

  it('keeps a stale conflict on its request and requires a refresh', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(api, 'resolveApproval').mockRejectedValue(new ApiRequestError('conflict', {
      status: 409, code: 'CONFLICT_VERSION_MISMATCH',
    }));
    render(<ApprovalList approvals={[pendingApproval]} followUps={[]} projectId="prj_ridge" onRefresh={onRefresh} />);

    const card = screen.getByRole('article');
    fireEvent.click(within(card).getByRole('button', { name: 'Reject' }));
    expect(await within(card).findByRole('alert')).toHaveTextContent(
      'This request has already been resolved. Refresh to see the latest status.',
    );
    expect(within(card).getByRole('button', { name: 'Approve' })).toBeDisabled();
    fireEvent.click(within(card).getByRole('button', { name: 'Refresh to see latest status' }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
