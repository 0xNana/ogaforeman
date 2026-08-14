// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  appendSpeechSegment,
  composerProgressMessage,
  SiteComposer,
  shouldShowAttachmentName,
} from './site-composer';

const apiMocks = vi.hoisted(() => ({
  sendConversationMessage: vi.fn(),
  uploadSiteMedia: vi.fn(),
  getAgentRun: vi.fn(),
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('site composer helpers', () => {
  it('keeps finalized voice segments when later recognition results arrive', () => {
    const first = appendSpeechSegment('', 'First-floor blockwork is complete.');
    const second = appendSpeechSegment(first, 'The electrician did not come.');

    expect(second).toBe(
      'First-floor blockwork is complete. The electrician did not come.',
    );
  });

  it('shows one concise progress message in the composer', () => {
    expect(composerProgressMessage('uploading')).toBe('Adding your attachment…');
    expect(composerProgressMessage('processing')).toBe('Checking the project…');
    expect(composerProgressMessage('updating')).toBe('Updating the project…');
    expect(composerProgressMessage('success')).toBeNull();
  });

  it('does not present the generated voice filename as a user attachment', () => {
    expect(shouldShowAttachmentName(new File([], 'site-voice-note.webm', { type: 'audio/webm' }))).toBe(false);
    expect(shouldShowAttachmentName(new File([], 'site-progress.jpg', { type: 'image/jpeg' }))).toBe(true);
  });
});

describe('universal OG composer', () => {
  it('routes text through the conversational intent endpoint', async () => {
    const onConversationResult = vi.fn();
    apiMocks.sendConversationMessage.mockResolvedValue({
      kind: 'advice',
      text: 'Hold plastering until the electrical blocker is cleared.',
      cited_record_ids: ['iss_electrical'],
      mutation_performed: false,
    });
    render(
      <SiteComposer
        projectId="prj_ridge"
        embedded
        onConversationResult={onConversationResult}
      />,
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'Message OG' }), {
      target: { value: 'wdyt about plastering tomorrow?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send to OG' }));

    await waitFor(() => expect(apiMocks.sendConversationMessage).toHaveBeenCalledOnce());
    expect(apiMocks.sendConversationMessage).toHaveBeenCalledWith(
      'prj_ridge',
      'wdyt about plastering tomorrow?',
      expect.stringMatching(/^conversation:/),
      { attachmentIds: [], inputType: 'text' },
    );
    expect(onConversationResult).toHaveBeenCalledWith(
      'wdyt about plastering tomorrow?',
      expect.objectContaining({ kind: 'advice' }),
    );
  });

  it('uploads a photo once and sends its verified id through the same conversation endpoint', async () => {
    apiMocks.uploadSiteMedia.mockResolvedValue({ success: true, attachmentId: 'att_photo123' });
    apiMocks.sendConversationMessage.mockResolvedValue({
      kind: 'workflow',
      text: 'I saved the update and started the site workflow.',
      workflow_run_id: 'run_photo123',
      cited_record_ids: [],
      mutation_performed: false,
    });
    apiMocks.getAgentRun.mockResolvedValue({
      id: 'run_photo123',
      run_id: 'run_photo123',
      status: 'completed',
      result_summary: 'Photo update processed.',
      pending_actions: [],
    });
    const { container } = render(<SiteComposer projectId="prj_ridge" embedded />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const photo = new File(['photo'], 'progress.jpg', { type: 'image/jpeg' });

    fireEvent.change(input!, { target: { files: [photo] } });
    fireEvent.click(screen.getByRole('button', { name: 'Send to OG' }));

    await waitFor(() => expect(apiMocks.sendConversationMessage).toHaveBeenCalledOnce());
    expect(apiMocks.sendConversationMessage).toHaveBeenCalledWith(
      'prj_ridge',
      '',
      expect.stringMatching(/^conversation:/),
      { attachmentIds: ['att_photo123'], inputType: 'photo' },
    );
    expect(await screen.findByText('Workflow receipt')).toBeVisible();
  });
});
