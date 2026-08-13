// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PhotoRegister } from './photo-register';

afterEach(cleanup);

const photo = { id: 'att_photo1', name: 'north-elevation.jpg', contentType: 'image/jpeg', date: '8 Aug 2026, 09:45', dateIso: '2026-08-08T09:45:00+00:00', uploadedBy: 'usr_kwame', location: 'North elevation', siteUpdateId: 'sup_1', taskIds: ['tsk_1'], issueIds: ['iss_1'], dailyLogIds: ['rpt_1'] };

describe('PhotoRegister', () => {
  it('filters persisted photos and exposes their related records', async () => {
    const loadUrl = vi.fn().mockResolvedValue('https://storage.test/photo.jpg');
    render(<PhotoRegister photos={[photo]} tasks={[{ id: 'tsk_1', title: 'Blockwork' }]} issues={[{ id: 'iss_1', description: 'Check joints' }]} dailyLogs={[{ id: 'rpt_1', date: 'Saturday, 8 August' }]} loadUrl={loadUrl} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open north-elevation.jpg' }));
    expect(await screen.findByRole('dialog', { name: 'north-elevation.jpg' })).toBeVisible();
    await waitFor(() => expect(loadUrl).toHaveBeenCalledWith('att_photo1'));
    expect(screen.getByText('Blockwork', { selector: 'dd' })).toBeVisible();
    expect(screen.getByText('Check joints')).toBeVisible();
    expect(screen.getByText('Saturday, 8 August')).toBeVisible();
    expect(screen.getByText('sup_1')).toBeVisible();
  });

  it('supports date, location, task, and uploader filters', () => {
    render(<PhotoRegister photos={[photo]} tasks={[{ id: 'tsk_1', title: 'Blockwork' }]} issues={[]} dailyLogs={[]} loadUrl={vi.fn().mockRejectedValue(new Error('unavailable'))} />);
    fireEvent.change(screen.getByLabelText('Filter photos by uploader'), { target: { value: 'someone-else' } });
    expect(screen.getByRole('heading', { name: 'No matching photos.' })).toBeVisible();
  });
});
