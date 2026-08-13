import { describe, expect, it } from 'vitest';

import {
  appendSpeechSegment,
  composerProgressMessage,
  shouldShowAttachmentName,
} from './site-composer';

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
