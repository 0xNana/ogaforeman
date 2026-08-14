// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OgConversation } from './og-conversation';

const apiMocks = vi.hoisted(() => ({
  sendConversationMessage: vi.fn(),
  uploadSiteMedia: vi.fn(),
  getAgentRun: vi.fn(),
  getPendingConversationProposal: vi.fn(),
  confirmConversationProposal: vi.fn(),
  cancelConversationProposal: vi.fn(),
}));
vi.mock('@/lib/api', () => ({
  api: apiMocks,
  ApiRequestError: class ApiRequestError extends Error {},
}));
vi.mock('@/components/project-context', () => ({
  useProject: () => ({ refresh: vi.fn() }),
}));
vi.mock('@/components/workflow-receipt', () => ({
  WorkflowReceipt: () => <div>Workflow receipt</div>,
}));

describe('OgConversation', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  beforeEach(() => {
    apiMocks.getPendingConversationProposal.mockResolvedValue({ proposal: null, memory_version: 0 });
  });

  it('renders grounded advice in a live conversation transcript', async () => {
    apiMocks.sendConversationMessage.mockResolvedValue({ kind: 'advice', text: "I'd hold off committing yet. Cement is low.", recommendation: 'hold', cited_record_ids: ['mat_cement'] });
    render(<OgConversation projectId="prj_ridge" />);

    expect(screen.getAllByRole('textbox', { name: 'Message OG' })).toHaveLength(1);

    fireEvent.change(screen.getByRole('textbox', { name: 'Message OG' }), { target: { value: 'wdyt about plastering tomorrow?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send to OG' }));

    await waitFor(() => expect(screen.getByText("I'd hold off committing yet. Cement is low.")).toBeVisible());
    expect(screen.getByText('ADVICE')).toBeVisible();
  });

  it('shows proposed changes separately from completed work', async () => {
    apiMocks.sendConversationMessage.mockResolvedValue({
      kind: 'proposed_change',
      text: 'Review this change.',
      proposed_action: 'Move plastering to Friday',
      memory_version: 4,
      proposal: {
        proposal_id: 'cpr_plastering', kind: 'schedule', project_id: 'prj_ridge',
        actor_id: 'usr_foreman', requested_action: 'Move plastering to Friday', created_at: '2026-08-14T10:00:00Z', expires_at: '2026-08-14T10:15:00Z',
        observed_memory_version: 3, observed_entity_versions: { tsk_plastering: 7 },
      },
      cited_record_ids: [],
    });
    render(<OgConversation projectId="prj_ridge" />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Message OG' }), { target: { value: 'move plastering to Friday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send to OG' }));

    await waitFor(() => expect(screen.getAllByText('PROPOSED CHANGE')).toHaveLength(2));
    expect(screen.queryByText('DONE')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('reloads and confirms the server-persisted proposal using only its id and memory version', async () => {
    apiMocks.getPendingConversationProposal.mockResolvedValue({
      memory_version: 9,
      proposal: {
        proposal_id: 'cpr_saved', kind: 'schedule', project_id: 'prj_ridge',
        actor_id: 'usr_foreman', requested_action: 'Move plastering to Friday', created_at: '2026-08-14T10:00:00Z', expires_at: '2026-08-14T10:15:00Z',
        observed_memory_version: 8, observed_entity_versions: { tsk_plastering: 7 },
      },
    });
    apiMocks.confirmConversationProposal.mockResolvedValue({ kind: 'done', text: 'Schedule updated.', cited_record_ids: [], mutation_performed: true });

    render(<OgConversation projectId="prj_ridge" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(apiMocks.confirmConversationProposal).toHaveBeenCalledWith('prj_ridge', 'cpr_saved', 9));
    expect(await screen.findByText('Schedule updated.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
  });
});
