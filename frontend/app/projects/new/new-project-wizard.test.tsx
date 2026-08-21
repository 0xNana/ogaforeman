// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { NewProjectWizard } from '@/components/new-project-wizard';

const { createProject, replace } = vi.hoisted(() => ({
  createProject: vi.fn(),
  replace: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ api: { createProject } }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));

describe('NewProjectWizard', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    createProject.mockResolvedValue({
      id: 'prj_ridge',
      name: 'Ridge House',
      location: 'East Legon',
      status: 'PLANNING',
      timezone: 'Africa/Accra',
    });
  });

  it('collects every supported project field and establishes an import setup URL', async () => {
    render(<NewProjectWizard />);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: ' Ridge House ' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: ' East Legon ' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Three-bedroom residential build' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Target end date'), { target: { value: '2027-04-30' } });
    fireEvent.change(screen.getByLabelText('Project status'), { target: { value: 'planning' } });
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Africa/Accra' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));

    expect(screen.getByRole('radio', { name: /Import an existing plan/ })).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledWith({
      name: 'Ridge House',
      location: 'East Legon',
      description: 'Three-bedroom residential build',
      timezone: 'Africa/Accra',
      start_date: '2026-09-01',
      target_end_date: '2027-04-30',
      status: 'planning',
    }, expect.stringMatching(/^project:/)));
    expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=import');
  });

  it('stages a selected Markdown file for import after creating the project', async () => {
    render(<NewProjectWizard ownerKey="firebase-user" />);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));

    const file = new File(['# Ridge plan\nTask: Foundation'], 'ridge-plan.md', { type: 'text/markdown' });
    Object.defineProperty(file, 'text', {
      value: vi.fn().mockResolvedValue('# Ridge plan\nTask: Foundation'),
    });
    fireEvent.change(screen.getByLabelText('Choose a .txt or .md file'), {
      target: { files: [file] },
    });

    expect(await screen.findByText('ridge-plan.md')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=import'));
    expect(JSON.parse(
      window.sessionStorage.getItem('oga:project-import:create-claim:prj_ridge') ?? '{}',
    )).toMatchObject({
      ownerKey: 'firebase-user',
      projectId: 'prj_ridge',
      source_name: 'ridge-plan.md',
      source_text: '# Ridge plan\nTask: Foundation',
      source_type: 'markdown',
      idempotencyKey: expect.stringMatching(/^project-import:/),
    });
  });

  it('rejects unsupported files before project creation', async () => {
    render(<NewProjectWizard />);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));
    fireEvent.change(screen.getByLabelText('Choose a .txt or .md file'), {
      target: { files: [new File(['PDF'], 'ridge-plan.pdf', { type: 'application/pdf' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Use a .txt or .md file');
    expect(createProject).not.toHaveBeenCalled();
  });

  it('retains one project-creation claim when a timed-out request is retried', async () => {
    createProject
      .mockRejectedValueOnce(new Error('request timed out'))
      .mockResolvedValueOnce({ id: 'prj_ridge' });
    render(<NewProjectWizard />);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));
    fireEvent.click(screen.getByRole('radio', { name: /Start empty/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('could not create');
    fireEvent.click(screen.getByRole('button', { name: 'Try creating again' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(2));
    expect(createProject.mock.calls[0][1]).toBe(createProject.mock.calls[1][1]);
    expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=empty');
  });

  it('restores the draft and retry claim after the wizard remounts', async () => {
    const firstRender = render(<NewProjectWizard />);
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Ridge House'));
    const storedKey = JSON.parse(window.sessionStorage.getItem('oga:new-project:create-claim') ?? '{}').idempotencyKey;

    firstRender.unmount();
    render(<NewProjectWizard />);
    expect(screen.getByRole('heading', { name: 'How do you want to set up the work?' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledWith(expect.any(Object), storedKey));
  });

  it('does not restore another signed-in user\'s project draft', async () => {
    const firstRender = render(<NewProjectWizard ownerKey="firebase-user-one" />);
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Private Site' } });
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Private Site'));

    firstRender.unmount();
    render(<NewProjectWizard ownerKey="firebase-user-two" />);

    expect(screen.getByLabelText('Project name')).toHaveValue('');
  });

  it('discards the retry claim when the user explicitly cancels', async () => {
    render(<NewProjectWizard />);
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Cancelled Site' } });
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Cancelled Site'));

    const cancel = screen.getByRole('link', { name: 'Cancel' });
    cancel.addEventListener('click', (event) => event.preventDefault());
    fireEvent.click(cancel);

    expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toBeNull();
  });

  it('blocks a target end date before the start date', () => {
    render(<NewProjectWizard />);

    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-02' } });
    fireEvent.change(screen.getByLabelText('Target end date'), { target: { value: '2026-09-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue to setup' }));

    expect(screen.getByRole('alert')).toHaveTextContent('cannot be before');
    expect(screen.queryByRole('heading', { name: 'How do you want to set up the work?' })).not.toBeInTheDocument();
  });
});
