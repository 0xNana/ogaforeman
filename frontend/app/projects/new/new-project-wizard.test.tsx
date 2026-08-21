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

  it('starts with file import and does not ask for duplicate project details', () => {
    render(<NewProjectWizard />);

    expect(screen.getByRole('heading', { name: 'Tell OG about the project.' })).toBeVisible();
    expect(screen.getByLabelText('Choose a project file')).toBeVisible();
    expect(screen.queryByLabelText('Project name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Location')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue with this file' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Enter project details manually' })).toBeVisible();
  });

  it('collects every supported project field on the manual fallback path', async () => {
    render(<NewProjectWizard />);

    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: ' Ridge House ' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: ' East Legon ' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Three-bedroom residential build' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Target end date'), { target: { value: '2027-04-30' } });
    fireEvent.change(screen.getByLabelText('Project status'), { target: { value: 'planning' } });
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Africa/Accra' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create empty project' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledWith({
      name: 'Ridge House',
      location: 'East Legon',
      description: 'Three-bedroom residential build',
      timezone: 'Africa/Accra',
      start_date: '2026-09-01',
      target_end_date: '2027-04-30',
      status: 'planning',
    }, expect.stringMatching(/^project:/)));
    expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=empty');
  });

  it('stages a selected Markdown file for import after creating the project', async () => {
    render(<NewProjectWizard ownerKey="firebase-user" />);

    const file = new File(['# Ridge plan\nTask: Foundation'], 'ridge-plan.md', { type: 'text/markdown' });
    Object.defineProperty(file, 'text', {
      value: vi.fn().mockResolvedValue('# Ridge plan\nTask: Foundation'),
    });
    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [file] },
    });

    expect(await screen.findByText('ridge-plan.md')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Continue with this file' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledWith({
      name: 'Ridge plan',
      location: 'Not specified',
      description: null,
      timezone: expect.any(String),
      start_date: null,
      target_end_date: null,
      status: 'planning',
    }, expect.stringMatching(/^project:/)));
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

  it('stages a selected Word document without browser-side text extraction', async () => {
    render(<NewProjectWizard ownerKey="firebase-user" />);

    const file = new File([new Uint8Array([80, 75, 3, 4])], 'ridge-plan.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    Object.defineProperty(file, 'arrayBuffer', {
      value: vi.fn().mockResolvedValue(Uint8Array.from([80, 75, 3, 4]).buffer),
    });
    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [file] },
    });
    expect(await screen.findByText('ridge-plan.docx')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Continue with this file' }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=import'));
    expect(JSON.parse(
      window.sessionStorage.getItem('oga:project-import:create-claim:prj_ridge') ?? '{}',
    )).toMatchObject({
      source_name: 'ridge-plan.docx',
      source_type: 'file',
      source_data_base64: 'UEsDBA==',
    });
  });

  it('rejects unsupported files before project creation', async () => {
    render(<NewProjectWizard />);

    fireEvent.change(screen.getByLabelText('Choose a project file'), {
      target: { files: [new File(['XER'], 'ridge-plan.xer', { type: 'application/octet-stream' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Use a Word, Excel, PDF, CSV, text, or Markdown file');
    expect(createProject).not.toHaveBeenCalled();
  });

  it('retains one project-creation claim when a timed-out request is retried', async () => {
    createProject
      .mockRejectedValueOnce(new Error('request timed out'))
      .mockResolvedValueOnce({ id: 'prj_ridge' });
    render(<NewProjectWizard />);

    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create empty project' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('could not create');
    fireEvent.click(screen.getByRole('button', { name: 'Try creating empty project again' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(2));
    expect(createProject.mock.calls[0][1]).toBe(createProject.mock.calls[1][1]);
    expect(replace).toHaveBeenCalledWith('/projects/prj_ridge/setup?method=empty');
  });

  it('restores the draft and retry claim after the wizard remounts', async () => {
    const firstRender = render(<NewProjectWizard />);
    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Ridge House'));
    const storedKey = JSON.parse(window.sessionStorage.getItem('oga:new-project:create-claim') ?? '{}').idempotencyKey;

    firstRender.unmount();
    render(<NewProjectWizard />);
    expect(screen.getByRole('heading', { name: 'Add the project details.' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Create empty project' }));

    await waitFor(() => expect(createProject).toHaveBeenCalledWith(expect.any(Object), storedKey));
  });

  it('does not restore another signed-in user\'s project draft', async () => {
    const firstRender = render(<NewProjectWizard ownerKey="firebase-user-one" />);
    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Private Site' } });
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Private Site'));

    firstRender.unmount();
    render(<NewProjectWizard ownerKey="firebase-user-two" />);

    expect(screen.queryByLabelText('Project name')).not.toBeInTheDocument();
  });

  it('discards the retry claim when the user explicitly cancels', async () => {
    render(<NewProjectWizard />);
    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Cancelled Site' } });
    await waitFor(() => expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toContain('Cancelled Site'));

    fireEvent.click(screen.getByRole('button', { name: 'Back to import' }));
    const cancel = screen.getByRole('link', { name: 'Cancel' });
    cancel.addEventListener('click', (event) => event.preventDefault());
    fireEvent.click(cancel);

    expect(window.sessionStorage.getItem('oga:new-project:create-claim')).toBeNull();
  });

  it('blocks a target end date before the start date', () => {
    render(<NewProjectWizard />);

    fireEvent.click(screen.getByRole('button', { name: 'Enter project details manually' }));
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Ridge House' } });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'East Legon' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-02' } });
    fireEvent.change(screen.getByLabelText('Target end date'), { target: { value: '2026-09-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create empty project' }));

    expect(screen.getByRole('alert')).toHaveTextContent('cannot be before');
    expect(screen.getByRole('heading', { name: 'Add the project details.' })).toBeVisible();
  });
});
