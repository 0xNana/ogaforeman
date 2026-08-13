import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { captureBrowserErrors, projectId, signInToProject } from './support';

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Manager mutation evidence runs once on desktop.');
  await signInToProject(page, testInfo);
});

test('manager views render task, material, report, and approval resources', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  const materialSuffix = Date.now().toString().slice(-8);

  await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible();

  await page.getByRole('link', { name: 'Documents' }).click();
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible();
  await expect(page.getByRole('row', { name: /Blockwork method statement.pdf/ })).toContainText('Not recorded');

  await page.getByRole('link', { name: 'Schedule' }).click();
  await expect(page.getByRole('heading', { name: 'Schedule', exact: true })).toBeVisible();
  await expect(page.getByRole('row', { name: /First-floor plastering/ })).toContainText('At risk');
  await page.getByRole('button', { name: 'Gantt' }).click();
  await expect(page.getByLabel('Schedule timeline')).toContainText('First-floor plastering');
  await expect(page.getByLabel('Schedule timeline')).toContainText('2 unscheduled activities');
  const scheduleAccessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(scheduleAccessibility.violations).toEqual([]);

  await page.getByRole('link', { name: 'Daily Logs' }).click();
  await expect(page.getByRole('heading', { name: 'Daily Logs', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Saturday, 8 August' })).toBeVisible();
  await expect(page.getByText('First-floor blockwork')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Delays / blockers' }).locator('..').getByText('Electrician absent')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Materials', exact: true }).locator('..').getByText('Cement stock is low')).toBeVisible();
  await expect(page.getByText('Compiled by OG from 1 site update')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit daily log' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Share daily log' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Export daily log' })).toBeEnabled();
  const dailyLogAccessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(dailyLogAccessibility.violations).toEqual([]);

  await page.getByRole('link', { name: 'Tasks' }).click();
  await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
  await page.getByRole('button', { name: 'Blocked' }).click();
  await expect(page.getByText('Electrical rough-in')).toBeVisible();

  await page.getByRole('link', { name: 'Issues' }).click();
  await expect(page.getByRole('heading', { name: 'Issues', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No matching issues.' })).toBeVisible();

  await page.getByRole('link', { name: 'Materials' }).click();
  await expect(page.getByRole('heading', { name: 'Materials' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Cement/ })).toBeVisible();
  await expect(page.getByText('50', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Requests' }).click();
  await expect(page.getByRole('heading', { name: 'No material requests.' })).toBeVisible();
  await page.getByRole('button', { name: 'Inventory' }).click();

  await page.getByRole('button', { name: 'Add material' }).click();
  await page.getByLabel('Material name 1').selectOption('custom');
  await page.getByLabel('Custom material name 1').fill(`Timber ${materialSuffix}`);
  await page.getByLabel('Unit 1').fill('pieces');
  await page.getByLabel('Available quantity 1').fill('12');
  await page.getByLabel('Minimum required 1').fill('8');
  await page.getByRole('button', { name: 'Add another material' }).click();
  await page.getByLabel('Material name 2').selectOption('custom');
  await page.getByLabel('Custom material name 2').fill(`Nails ${materialSuffix}`);
  await page.getByLabel('Unit 2').fill('pieces');
  await page.getByLabel('Available quantity 2').fill('200');
  await page.getByLabel('Minimum required 2').fill('100');
  await page.getByRole('button', { name: 'Add 2 materials' }).click();
  await expect(page.getByRole('row', { name: new RegExp(`Timber ${materialSuffix}`) })).toBeVisible();
  await expect(page.getByRole('row', { name: new RegExp(`Nails ${materialSuffix}`) })).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(accessibility.violations).toEqual([]);

  await page.getByRole('link', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'Daily report', exact: true })).toBeVisible();
  await expect(page.getByText('OG Foreman · Ridge House')).toBeVisible();
  const materialsSection = page.locator('.report-section').filter({
    has: page.getByRole('heading', { name: 'Materials', exact: true }),
  });
  await expect(materialsSection.getByText('Cement stock is low')).toBeVisible();

  await page.locator('.needs-you-link').click();
  await expect(page.getByRole('heading', { name: 'Needs you' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Approve desktop access sequence' })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('manager can approve and reject decisions and persistence survives reload', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await page.goto(`/projects/${projectId}/approvals`);

  const approveCard = page.getByRole('article').filter({ hasText: 'Approve desktop access sequence' });
  const refreshedSnapshot = page.waitForRequest((request) => (
    request.method() === 'GET' && request.url().endsWith(`/projects/${projectId}/snapshot`)
  ));
  await approveCard.getByRole('button', { name: 'Approve' }).click();
  await refreshedSnapshot;
  await expect(approveCard.getByText('APPROVED')).toBeVisible();
  await expect(approveCard.getByRole('status')).toContainText('OG is resuming from the saved checkpoint.');
  await expect(approveCard.getByRole('link', { name: 'Follow in activity' })).toHaveAttribute(
    'href',
    `/projects/${projectId}/activity`,
  );

  const rejectCard = page.getByRole('article').filter({ hasText: 'Reject desktop access sequence' });
  await rejectCard.getByRole('button', { name: 'Reject' }).click();
  await expect(rejectCard.getByText('REJECTED')).toBeVisible();
  await expect(rejectCard.getByRole('status')).toContainText('No supplier or external action will run.');

  await page.reload();
  await expect(page.getByRole('article').filter({ hasText: 'Approve desktop access sequence' }).getByText('APPROVED')).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: 'Reject desktop access sequence' }).getByText('REJECTED')).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('stale approval decision displays a recoverable conflict', async ({ page, request }) => {
  const browserErrors = captureBrowserErrors(page);
  await page.goto(`/projects/${projectId}/approvals`);
  const staleCard = page.getByRole('article').filter({ hasText: 'Stale desktop access sequence' });
  await expect(staleCard.getByText('PENDING')).toBeVisible();

  const concurrentDecision = await request.post(
    `http://127.0.0.1:8001/api/v1/projects/${projectId}/approvals/apr_stale_desktop123/decision`,
    {
      data: { decision: 'approved', expected_version: 0 },
      headers: {
        Authorization: 'Bearer local-e2e-token',
        'Idempotency-Key': 'approval:playwright:concurrent',
      },
    },
  );
  expect(concurrentDecision.ok()).toBe(true);

  await staleCard.getByRole('button', { name: 'Reject' }).click();
  await expect(page.locator('.status-banner[role="alert"]')).toContainText('This approval changed after you opened it.');
  await expect(page.getByRole('button', { name: 'Refresh approvals' })).toBeVisible();
  expect(browserErrors.filter((message) => !message.includes('409 (Conflict)'))).toEqual([]);
  expect(browserErrors.some((message) => message.includes('409 (Conflict)'))).toBe(true);
});
