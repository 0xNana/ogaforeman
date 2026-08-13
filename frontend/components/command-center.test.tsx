// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CommandCenter } from './command-center';
import type { ProjectSnapshot } from '@/lib/api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const snapshot = {
  project: {
    id: 'prj_ridge',
    name: 'Ridge House',
    location: 'East Legon',
    status: 'ACTIVE',
    timezone: 'Africa/Accra',
  },
  tasks: [],
  materials: [],
  approvals: [],
  activities: Array.from({ length: 7 }, (_, index) => ({
    id: `act_${index + 1}`,
    kind: 'update' as const,
    title: `Activity ${index + 1}`,
    description: `Update ${index + 1}`,
    date: `0${index + 1}:00`,
    user: 'OG',
  })),
  report: {
    date: 'Today',
    completed: [],
    inProgress: [],
    blocked: [],
    materials: [],
    tomorrow: [],
    risks: [],
    photos: [],
  },
} satisfies ProjectSnapshot;

describe('CommandCenter', () => {
  afterEach(cleanup);

  it('guides a new project through setup before the first site update', () => {
    render(<CommandCenter snapshot={{
      ...snapshot,
      activities: [],
      report: { ...snapshot.report, date: 'No report yet' },
    }} />);

    expect(screen.getByRole('heading', { name: 'Set up your first site.' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Add your first task' })).toHaveAttribute(
      'href',
      '/projects/prj_ridge/tasks',
    );
    expect(screen.getByRole('link', { name: 'Add project materials' })).toHaveAttribute(
      'href',
      '/projects/prj_ridge/materials',
    );
    expect(screen.getByRole('link', { name: 'Send the first site update' })).toHaveAttribute(
      'href',
      '/projects/prj_ridge/site',
    );
  });

  it('summarizes project status, attention, today, and lookahead from snapshot records', () => {
    render(<CommandCenter snapshot={{
      ...snapshot,
      tasks: [
        { id: 'tsk_done', title: 'Blockwork F1', status: 'COMPLETED', assignee: 'Mason team', dueLabel: 'Aug 13' },
        { id: 'tsk_blocked', title: 'Electrical rough-in', status: 'BLOCKED', assignee: 'Electrical team', dueLabel: 'Aug 15', blocking: 'Ceiling installation', note: 'Electrician absent' },
        { id: 'tsk_next', title: 'Plastering F1', status: 'PENDING', assignee: 'Finishes team', dueLabel: 'Aug 18' },
      ],
      approvals: [{ id: 'apr_cement', type: 'material_request', title: 'Cement request', status: 'PENDING', quantity: '90 bags', neededBy: 'Tomorrow', reason: '10 bags on site against 100 required.', requestedBy: 'OG', date: '10:17', version: 1 }],
      report: {
        ...snapshot.report,
        completed: ['Ground-floor blockwork'],
        inProgress: ['Plumbing rough-in'],
        blocked: ['Electrical contractor absent'],
        tomorrow: ['Start plastering'],
      },
    }} />);

    expect(screen.getByRole('heading', { name: 'Project overview' })).toBeVisible();
    expect(screen.getByLabelText('Project status metrics')).toHaveTextContent('Overall progress33%');
    expect(screen.getByLabelText('Project status metrics')).toHaveTextContent('Target completionNot set');
    expect(screen.getByLabelText('Project status metrics')).toHaveTextContent('Open issues1');
    expect(screen.getByLabelText('Project status metrics')).toHaveTextContent('Work at risk1');
    expect(screen.getByRole('heading', { name: 'Needs Attention' })).toBeVisible();
    expect(screen.getByText('Cement request')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Electrical rough-in' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Today' })).toBeVisible();
    expect(screen.getByText('Ground-floor blockwork')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Two-Week Lookahead' })).toBeVisible();
    expect(screen.getByRole('row', { name: /Blockwork F1/ })).toHaveTextContent('100%');
    expect(screen.getByRole('row', { name: /Electrical rough-in/ })).toHaveTextContent('Blocked');
    expect(screen.getByLabelText('OG noticed')).toHaveTextContent('Electrical rough-in is blocking Ceiling installation');
  });

  it('shows calm, explicit empty states without inventing site activity', () => {
    render(<CommandCenter snapshot={{ ...snapshot, activities: [] }} />);

    expect(screen.getByText('Nothing needs attention.')).toBeVisible();
    expect(screen.getByText('No work has been reported for today.')).toBeVisible();
    expect(screen.getByText('No tasks are available for the lookahead.')).toBeVisible();
  });
});
