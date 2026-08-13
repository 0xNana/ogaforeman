// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { WorkflowReceipt } from './workflow-receipt';

afterEach(cleanup);

describe('WorkflowReceipt', () => {
  it('presents completed work as an operational OG handoff', () => {
    render(<WorkflowReceipt outcome="completed" projectId="prj_1" summary="Blockwork was marked complete." />);
    expect(screen.getByText('DONE')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'OG handled it.' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'OG handled' })).toBeVisible();
    expect(screen.queryByText(/agent|tool|model|workflow/i)).not.toBeInTheDocument();
  });

  it('makes manager decisions explicit and links to review', () => {
    render(<WorkflowReceipt outcome="waiting_for_approval" projectId="prj_1" summary="Safe updates are saved." pendingActions={['Approve 30 bags of cement.', 'Review plastering risk.']} />);
    expect(screen.getByText('NEEDS YOU')).toBeVisible();
    expect(screen.getByText('Approve 30 bags of cement.')).toBeVisible();
    expect(screen.getByRole('link', { name: /Review approval/ })).toHaveAttribute('href', '/projects/prj_1/approvals');
  });
});
