// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Activity } from '@/lib/api';
import { ActivityStream } from './activity-stream';

afterEach(cleanup);

const activities: Activity[] = [
  {
    id: 'act_approval', kind: 'approval', title: 'Material request approved', description: 'Material request approved',
    date: '10:18', dateLabel: 'Saturday, 8 August 2026', occurredAt: '2026-08-08T10:18:00Z',
    user: 'usr_manager', actorType: 'user', action: 'approval.approved', entityType: 'approval', entityId: 'apr_cement',
  },
  {
    id: 'act_task', kind: 'progress', title: 'Blockwork completed', description: 'Blockwork completed',
    date: '10:15', dateLabel: 'Saturday, 8 August 2026', occurredAt: '2026-08-08T10:15:00Z',
    user: 'OG', actorType: 'agent', action: 'task.completed', entityType: 'task', entityId: 'tsk_blockwork',
  },
  {
    id: 'act_report', kind: 'report', title: 'Daily report published', description: 'Daily report published',
    date: '17:30', dateLabel: 'Friday, 7 August 2026', occurredAt: '2026-08-07T17:30:00Z',
    user: 'OG', actorType: 'system', action: 'report.published', entityType: 'daily_report', entityId: 'rpt_daily',
  },
];

describe('ActivityStream', () => {
  it('renders a chronological, date-grouped audit stream with object links', () => {
    render(<ActivityStream activities={activities} projectId="prj_ridge" />);

    const dates = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent);
    expect(dates).toEqual(['Saturday, 8 August 2026', 'Friday, 7 August 2026']);
    const entries = screen.getAllByRole('listitem');
    expect(within(entries[0]).getByText('Material request approved')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Approval' })).toHaveAttribute('href', '/projects/prj_ridge/approvals');
    expect(screen.getByRole('link', { name: 'Task' })).toHaveAttribute('href', '/projects/prj_ridge/tasks');
    expect(screen.queryByText(/apr_cement|tsk_blockwork|rpt_daily|usr_manager/)).not.toBeInTheDocument();
    expect(screen.getByText('Project member')).toBeVisible();
  });

  it('filters by workflow area and actor without losing the audit context', () => {
    render(<ActivityStream activities={activities} projectId="prj_ridge" />);

    fireEvent.click(screen.getByRole('button', { name: 'Tasks' }));
    expect(screen.getByText('Blockwork completed')).toBeVisible();
    expect(screen.queryByText('Material request approved')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'People' }));
    expect(screen.getByText('Material request approved')).toBeVisible();
    expect(screen.queryByText('Blockwork completed')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'OG' }));
    expect(screen.getByText('Blockwork completed')).toBeVisible();
    expect(screen.getByText('Daily report published')).toBeVisible();
  });

  it('paginates long audit trails and resets pagination when filtering', () => {
    const longTrail = Array.from({ length: 21 }, (_, index): Activity => ({
      ...activities[1],
      id: `act_task_${index}`,
      title: `Task activity ${index + 1}`,
      description: `Task activity ${index + 1}`,
    }));
    render(<ActivityStream activities={longTrail} projectId="prj_ridge" />);

    expect(screen.getAllByRole('listitem')).toHaveLength(20);
    expect(screen.getByText('Page 1 of 2')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /Next/ }));
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('Task activity 21')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'People' }));
    expect(screen.queryByText('Page 2 of 2')).not.toBeInTheDocument();
    expect(screen.getByText('No activity matches this filter.')).toBeVisible();
  });
});
