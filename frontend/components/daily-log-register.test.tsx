// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DailyLogRegister } from './daily-log-register';

const logs = [{ id: 'rpt_13', date: 'Thursday, 13 August', dateIso: '2026-08-13', summary: 'Blockwork moved and cement is low.', crew: null, weather: null, completed: ['Ground-floor blockwork'], inProgress: [], blocked: ['Electrician absent'], materials: ['Cement stock is low'], deliveries: [], inspections: [], photos: [], tomorrow: ['Start plastering'], risks: ['Electrician absent', 'Cement stock is low'], sourceUpdateCount: 3, status: 'PUBLISHED', version: 2 }];

afterEach(cleanup);

describe('DailyLogRegister', () => {
  it('renders a client-ready persisted daily log without inventing missing fields', () => {
    render(<DailyLogRegister projectName="Ridge House" projectId="prj_ridge" logs={logs} onRefresh={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Thursday, 13 August' })).toBeVisible();
    expect(screen.getByText('Ground-floor blockwork')).toBeVisible();
    expect(screen.getAllByText('Not recorded', { selector: 'dd' })).toHaveLength(2);
    expect(screen.getByText('Compiled by OG from 3 site updates')).toBeVisible();
  });

  it('searches historical logs and exposes share, export, and edit actions', () => {
    render(<DailyLogRegister projectName="Ridge House" projectId="prj_ridge" logs={logs} onRefresh={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Edit daily log' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Share daily log' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Export daily log' })).toBeEnabled();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search daily logs' }), { target: { value: 'missing' } });
    expect(screen.getByRole('heading', { name: 'No matching daily logs.' })).toBeVisible();
  });
});
