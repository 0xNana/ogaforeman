import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('project-list failure has one recovery action instead of an empty-state create CTA', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Project-list evidence runs once on desktop.');

  await page.route('**/api/v1/projects', async (route, request) => {
    if (request.method() === 'GET') {
      await route.abort('failed');
      return;
    }
    await route.continue();
  });

  const email = `project-list-${Date.now()}@example.test`;
  await page.goto('/sign-up?next=/projects');
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();

  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.locator('.projects-empty[role="alert"]')).toContainText('We could not load your projects.');
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'New project' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Create a project' })).toHaveCount(0);
});

test('empty project list keeps one canonical create action', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Project-list evidence runs once on desktop.');

  await page.route('**/api/v1/projects', async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      });
      return;
    }
    await route.continue();
  });

  const email = `empty-project-list-${Date.now()}@example.test`;
  await page.goto('/sign-up?next=/projects');
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();

  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByRole('heading', { name: 'Your AI Site Coordinator.' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Create your first project' })).toHaveAttribute('href', '/projects/new');
  await expect(page.getByRole('link', { name: 'New project' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Create a project' })).toHaveCount(0);
});

test('new-project retry keeps one project and lands on its reload-safe setup URL', async ({ page }) => {
  let createAttempts = 0;
  await page.route('**/api/v1/projects', async (route, request) => {
    if (request.method() === 'POST' && createAttempts++ === 0) {
      await route.fetch();
      await route.abort('failed');
      return;
    }
    await route.continue();
  });

  const email = `new-project-${Date.now()}@example.test`;
  const projectName = `PI06 Retry House ${Date.now()}`;
  await page.goto('/sign-up?next=/projects');
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();

  await page.getByRole('link', { name: /^(Create your first project|New project)$/ }).click();
  await expect(page).toHaveURL(/\/projects\/new$/);
  await page.getByLabel('Project name').fill(projectName);
  await page.getByLabel('Location').fill('East Legon, Accra');
  await page.getByLabel('Description').fill('Three-bedroom residential build');
  await page.getByLabel('Start date').fill('2026-09-01');
  await page.getByLabel('Target end date').fill('2027-04-30');
  await page.getByRole('button', { name: 'Continue to setup' }).click();
  await page.getByRole('radio', { name: /Start empty/ }).check();
  const accessibility = await new AxeBuilder({ page })
    .include('.new-project-card')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole('button', { name: 'Create project' }).click();

  await expect(page.locator('.form-alert')).toContainText('could not create');
  await page.getByRole('button', { name: 'Try creating again' }).click();
  await expect(page).toHaveURL(/\/projects\/prj_[a-z0-9]+\/setup\?method=empty$/);
  await expect(page.getByRole('heading', { name: 'Your empty project is ready.' })).toBeVisible();

  await page.goto('/projects');
  await expect(page.getByRole('link', { name: new RegExp(projectName) })).toHaveCount(1);
});

test('new-project import rejects unsupported files and recovers a committed extraction after reload', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  const email = `project-import-${Date.now()}@example.test`;
  const projectName = `PI07 Import House ${Date.now()}`;
  await page.goto('/sign-up?next=/projects/new');
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();

  await page.getByLabel('Project name').fill(projectName);
  await page.getByLabel('Location').fill('East Legon, Accra');
  await page.getByRole('button', { name: 'Continue to setup' }).click();
  await page.getByLabel('Choose a project file').setInputFiles({
    name: 'plan.xer',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('Primavera unsupported'),
  });
  await expect(page.locator('.form-alert')).toContainText('Use a Word, Excel, PDF, CSV, text, or Markdown file');
  await page.getByLabel('Choose a project file').setInputFiles({
    name: 'ridge-plan.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Task: Excavation\nTask: Foundation'),
  });
  await expect(page.getByText('ridge-plan.csv')).toBeVisible();
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page).toHaveURL(/\/projects\/prj_[a-z0-9]+\/setup\?method=import$/);
  await expect(page.getByRole('heading', { name: 'Add your project plan.' })).toBeVisible();
  await expect(page.getByText('ridge-plan.csv')).toBeVisible();

  const accessibility = await new AxeBuilder({ page })
    .include('.project-import-setup')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);

  let importRequests = 0;
  await page.route('**/api/v1/projects/*/imports', async (route, request) => {
    if (request.method() === 'POST') importRequests += 1;
    await route.continue();
  });
  expect(importRequests).toBe(0);

  await page.unroute('**/api/v1/projects/*/imports');
  let committedResponseLost = false;
  await page.route('**/api/v1/projects/*/imports', async (route, request) => {
    if (request.method() === 'POST') {
      importRequests += 1;
      if (!committedResponseLost) {
        committedResponseLost = true;
        await route.fetch();
        await route.abort('failed');
        return;
      }
    }
    await route.continue();
  });
  await page.getByRole('button', { name: 'Extract project plan' }).click();
  await expect(page.locator('.form-alert')).toContainText('saved in this tab');
  expect(consoleErrors).toEqual(['Failed to load resource: net::ERR_FAILED']);
  consoleErrors.length = 0;

  await page.reload();
  await expect(page).toHaveURL(/\/projects\/prj_[a-z0-9]+\/imports\/imp_[a-z0-9]+$/);
  await expect(page.getByRole('heading', { name: 'Review project initialization' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Excavation/ })).toBeVisible();
  expect(importRequests).toBe(1);
  expect(consoleErrors).toEqual([]);
});
