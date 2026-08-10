// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CommandCenter } from './command-center';
import type { ProjectSnapshot } from '@/lib/api';

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
    user: 'Oga',
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

  it('paginates dashboard activity without changing the total update count', () => {
    render(<CommandCenter snapshot={snapshot} />);

    expect(screen.getByText('7 updates')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Activity 1' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Activity 6' })).not.toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Previous activity page' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Next activity page' }));

    expect(screen.queryByRole('heading', { name: 'Activity 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Activity 6' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Activity 7' })).toBeVisible();
    expect(screen.getByText('Page 2 of 2')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Next activity page' })).toBeDisabled();
  });
});
