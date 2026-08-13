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
  await expect(page.getByRole('button', { name: 'New project' })).toHaveCount(0);
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
  await expect(page.getByRole('button', { name: 'Create your first project' })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'New project' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Create a project' })).toHaveCount(0);
});
