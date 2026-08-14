// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OgConversation } from './og-conversation';

const { sendConversationMessage } = vi.hoisted(() => ({ sendConversationMessage: vi.fn() }));
vi.mock('@/lib/api', () => ({
  api: { sendConversationMessage },
  ApiRequestError: class ApiRequestError extends Error {},
}));
vi.mock('@/components/site-composer', () => ({ SiteComposer: () => <div>Multimodal site update</div> }));

describe('OgConversation', () => {
  afterEach(() => { cleanup(); sendConversationMessage.mockReset(); });

  it('renders grounded advice in a live conversation transcript', async () => {
    sendConversationMessage.mockResolvedValue({ kind: 'advice', text: "I'd hold off committing yet. Cement is low.", recommendation: 'hold', cited_record_ids: ['mat_cement'] });
    render(<OgConversation projectId="prj_ridge" />);

    fireEvent.change(screen.getByRole('textbox', { name: 'Message OG' }), { target: { value: 'wdyt about plastering tomorrow?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => expect(screen.getByText("I'd hold off committing yet. Cement is low.")).toBeVisible());
    expect(screen.getByText('ADVICE')).toBeVisible();
  });

  it('shows proposed changes separately from completed work', async () => {
    sendConversationMessage.mockResolvedValue({ kind: 'proposed_change', text: 'Review this change.', proposed_action: 'Move plastering to Friday', cited_record_ids: [] });
    render(<OgConversation projectId="prj_ridge" />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Message OG' }), { target: { value: 'move plastering to Friday' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => expect(screen.getByText('PROPOSED CHANGE')).toBeVisible());
    expect(screen.queryByText('DONE')).not.toBeInTheDocument();
  });
});
