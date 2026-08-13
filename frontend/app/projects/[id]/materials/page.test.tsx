// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MaterialsPage from './page';


const { refresh, createMaterial } = vi.hoisted(() => ({
  refresh: vi.fn(),
  createMaterial: vi.fn(),
}));

vi.mock('@/components/project-context', () => ({
  useProject: () => ({
    projectId: 'prj_ridge',
    refresh,
    snapshot: { materials: [] },
  }),
}));

vi.mock('@/lib/api', () => ({
  api: { createMaterial },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

describe('MaterialsPage', () => {
  beforeEach(() => {
    createMaterial.mockReset();
    createMaterial.mockResolvedValue({});
    refresh.mockReset();
    refresh.mockResolvedValue(undefined);
  });

  it('lets a project manager add multiple materials in one submission', async () => {
    render(<MaterialsPage />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Add material' })[0]);
    fireEvent.change(screen.getByLabelText('Material name 1'), {
      target: { value: 'Cement' },
    });
    fireEvent.change(screen.getByLabelText('Available quantity 1'), {
      target: { value: '20' },
    });
    fireEvent.change(screen.getByLabelText('Minimum required 1'), {
      target: { value: '10' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add another material' }));
    fireEvent.change(screen.getByLabelText('Material name 2'), {
      target: { value: 'custom' },
    });
    fireEvent.change(screen.getByLabelText('Custom material name 2'), {
      target: { value: 'Sharp sand' },
    });
    fireEvent.change(screen.getByLabelText('Unit 2'), {
      target: { value: 'loads' },
    });
    fireEvent.change(screen.getByLabelText('Available quantity 2'), {
      target: { value: '8' },
    });
    fireEvent.change(screen.getByLabelText('Minimum required 2'), {
      target: { value: '4' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add 2 materials' }));

    await waitFor(() => expect(createMaterial).toHaveBeenCalledTimes(2));
    expect(createMaterial).toHaveBeenNthCalledWith(1, 'prj_ridge', {
      name: 'Cement',
      unit: 'bags',
      available_quantity: 20,
      minimum_required_quantity: 10,
    });
    expect(createMaterial).toHaveBeenNthCalledWith(2, 'prj_ridge', {
      name: 'Sharp sand',
      unit: 'loads',
      available_quantity: 8,
      minimum_required_quantity: 4,
    });
    expect(refresh).toHaveBeenCalledOnce();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('does not resubmit materials that succeeded before a later row failed', async () => {
    createMaterial
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('Nails could not be added.'))
      .mockResolvedValueOnce({});
    render(<MaterialsPage />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Add material' })[0]);
    fireEvent.change(screen.getByLabelText('Material name 1'), {
      target: { value: 'Cement' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add another material' }));
    fireEvent.change(screen.getByLabelText('Material name 2'), {
      target: { value: 'Nails' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add 2 materials' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '1 material added. Nails could not be added.',
    );
    expect(screen.queryByDisplayValue('Cement')).not.toBeInTheDocument();
    expect(screen.getByDisplayValue('Nails')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add 1 material' }));

    await waitFor(() => expect(createMaterial).toHaveBeenCalledTimes(3));
    expect(createMaterial).toHaveBeenLastCalledWith('prj_ridge', {
      name: 'Nails',
      unit: 'boxes',
      available_quantity: 0,
      minimum_required_quantity: 0,
    });
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
