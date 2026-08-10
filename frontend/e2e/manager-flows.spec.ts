import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { captureBrowserErrors, signInToProject } from './support';

test('desktop command center and activity use API projections', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop evidence runs in Chromium desktop.');
  const browserErrors = captureBrowserErrors(page);

  await signInToProject(page, testInfo);
  await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
  await expect(page.getByLabel('Today summary')).toContainText('Completed0');
  await expect(page.getByLabel('Today summary')).toContainText('Needs attention7');
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'First-floor blockwork completed.' })).toBeVisible();
  await expect(page.getByLabel('Type a site update')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add attachment' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Start voice recording' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Site update' })).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);

  await page.getByRole('link', { name: 'Activity' }).click();
  await expect(page).toHaveURL(/\/activity$/);
  await expect(page.getByRole('heading', { name: 'What Oga has handled' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Electrical work is blocked by the absent electrician.' })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('mobile command center navigation remains usable without overflow', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Mobile evidence runs with the Pixel viewport.');
  const browserErrors = captureBrowserErrors(page);

  await signInToProject(page, testInfo);
  await expect(page.getByRole('button', { name: 'Open project menu' })).toBeVisible();
  await page.getByRole('button', { name: 'Open project menu' }).click();
  await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
  await page.getByRole('link', { name: 'Activity' }).click();
  await expect(page.getByRole('heading', { name: 'What Oga has handled' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Cement shortage detected and sent for approval.' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(browserErrors).toEqual([]);
});
