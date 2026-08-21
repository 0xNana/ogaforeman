import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

async function startImportReview(page: Page, label: string): Promise<{ projectId: string; projectName: string }> {
  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const sourceProjectName = `${label} ${nonce}`;
  const reviewedProjectName = 'Imported project plan';
  await page.goto('/sign-up?next=/projects/new');
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(`pi08-${nonce}@example.test`);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();

  await page.getByLabel('Choose a project file').setInputFiles({
    name: 'ridge-project.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from(`# ${sourceProjectName}\nLocation: East Legon, Accra\nTask: Excavation\nTask: Foundation`),
  });
  await page.getByRole('button', { name: 'Continue with this file' }).click();
  await expect(page).toHaveURL(/\/projects\/prj_[a-z0-9]+\/imports\/imp_[a-z0-9]+$/);
  const projectId = page.url().match(/\/projects\/(prj_[a-z0-9]+)\/imports/)?.[1];
  expect(projectId).toBeTruthy();

  await expect(page.getByRole('heading', { name: 'Review project initialization' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Project details' })).toBeVisible();
  await expect(page.getByText(reviewedProjectName)).toBeVisible();
  return { projectId: projectId!, projectName: reviewedProjectName };
}

test('review confirmation survives response loss and opens refreshed canonical state', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile-chromium') await page.setViewportSize({ width: 360, height: 800 });
  const { projectId, projectName } = await startImportReview(page, 'PI08 Confirm House');

  const accessibility = await new AxeBuilder({ page })
    .include('.import-review-page')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);

  const confirm = page.getByRole('button', { name: 'Confirm & Initialize' });
  await confirm.focus();
  await expect(confirm).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Cancel Import' })).toBeFocused();

  let confirmRequests = 0;
  let committedResponseLost = false;
  await page.route(`**/api/v1/projects/${projectId}/imports/*/confirm`, async (route, request) => {
    if (request.method() === 'POST') {
      confirmRequests += 1;
      if (!committedResponseLost) {
        committedResponseLost = true;
        await route.fetch();
        await route.abort('failed');
        return;
      }
    }
    await route.continue();
  });

  await confirm.click();
  await expect(page.locator('.form-error[role="alert"]')).toContainText('could not reach');
  expect(confirmRequests).toBe(1);

  const refreshedSnapshot = page.waitForResponse((response) => (
    response.url().endsWith(`/api/v1/projects/${projectId}/snapshot`)
    && response.request().method() === 'GET'
    && response.ok()
  ));
  await page.getByRole('button', { name: 'Confirm & Initialize' }).click();
  const snapshot = await (await refreshedSnapshot).json() as { tasks: Array<{ title: string }> };

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}$`));
  expect(snapshot.tasks.filter((task) => task.title === 'Excavation')).toHaveLength(1);
  expect(snapshot.tasks.filter((task) => task.title === 'Foundation')).toHaveLength(1);
  expect(confirmRequests).toBe(2);
  if (testInfo.project.name === 'mobile-chromium') {
    await expect(page.getByRole('heading', { name: projectName })).toBeVisible();
  } else {
    await expect(page.getByRole('heading', { name: 'Project overview' })).toBeVisible();
  }
});

test('review cancellation survives response loss and returns to import setup', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile-chromium') await page.setViewportSize({ width: 360, height: 800 });
  const { projectId } = await startImportReview(page, 'PI08 Cancel House');

  let cancelRequests = 0;
  let committedResponseLost = false;
  await page.route(`**/api/v1/projects/${projectId}/imports/*/cancel`, async (route, request) => {
    if (request.method() === 'POST') {
      cancelRequests += 1;
      if (!committedResponseLost) {
        committedResponseLost = true;
        await route.fetch();
        await route.abort('failed');
        return;
      }
    }
    await route.continue();
  });

  await page.getByRole('button', { name: 'Cancel Import' }).click();
  await expect(page.locator('.form-error[role="alert"]')).toContainText('could not reach');
  expect(cancelRequests).toBe(1);
  await page.getByRole('button', { name: 'Cancel Import' }).click();

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/setup\\?method=import$`));
  await expect(page.getByRole('heading', { name: 'Add your project plan.' })).toBeVisible();
  expect(cancelRequests).toBe(2);
});
