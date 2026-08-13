import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { captureBrowserErrors, signInToProject } from './support';

test('desktop command center and activity use API projections', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop evidence runs in Chromium desktop.');
  const browserErrors = captureBrowserErrors(page);

  await signInToProject(page, testInfo);
  await expect(page.getByRole('button', { name: 'Sign Out' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Project overview' })).toBeVisible();
  await expect(page.getByLabel('Project status metrics')).toContainText('Overall progress');
  await expect(page.getByLabel('Project status metrics')).toContainText('Open issues');
  await expect(page.getByRole('heading', { name: 'Needs Attention' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Two-Week Lookahead' })).toBeVisible();
  await expect(page.getByRole('row', { name: /First-floor blockwork/ })).toBeVisible();
  await expect(page.getByLabel('Type a site update')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add attachment' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Start voice recording' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Site update' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Ask OG' })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search project' })).toBeVisible();

  await page.getByRole('button', { name: 'Ask OG' }).click();
  const ogDrawer = page.getByRole('dialog', { name: 'Ask OG' });
  await expect(ogDrawer).toBeVisible();
  await expect(ogDrawer.getByText("What's happening on site?")).toBeVisible();
  await expect(ogDrawer.getByLabel('Type a site update')).toBeVisible();
  await expect(ogDrawer.getByRole('button', { name: 'Add attachment' })).toBeVisible();
  await expect(ogDrawer.getByRole('button', { name: 'Start voice recording' })).toBeVisible();
  const ogAccessibility = await new AxeBuilder({ page }).include('.og-drawer').withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(ogAccessibility.violations).toEqual([]);
  await ogDrawer.getByRole('button', { name: 'Close Ask OG' }).click();

  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);

  await page.getByRole('link', { name: 'Activity' }).click();
  await expect(page).toHaveURL(/\/activity$/);
  await expect(page.getByRole('heading', { name: 'What OG has handled' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Electrical work is blocked by the absent electrician\./ })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('mobile command center navigation remains usable without overflow', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Mobile evidence runs with the Pixel viewport.');
  const browserErrors = captureBrowserErrors(page);

  await signInToProject(page, testInfo);
  await expect(page.getByRole('navigation', { name: 'Mobile project navigation' })).toBeVisible();
  await page.getByRole('button', { name: 'OG' }).click();
  const ogSheet = page.getByRole('dialog', { name: 'Ask OG' });
  await expect(ogSheet).toBeVisible();
  await expect.poll(async () => ogSheet.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return box.left === 0 && box.width === window.innerWidth && box.height === window.innerHeight;
  })).toBe(true);
  await ogSheet.getByRole('button', { name: 'Close Ask OG' }).click();
  await page.getByRole('link', { name: 'Tasks' }).click();
  await page.getByRole('button', { name: 'Electrical rough-in' }).click();
  await expect(page.getByRole('dialog', { name: 'Electrical rough-in' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Close details' }).click();
  await page.getByRole('button', { name: 'More' }).click();
  await expect(page.getByRole('dialog', { name: 'More sections' })).toBeVisible();
  await page.getByRole('link', { name: 'Schedule' }).click();
  await page.getByRole('button', { name: 'Gantt' }).click();
  await expect(page.getByLabel('Schedule timeline')).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'More' }).click();
  await page.getByRole('link', { name: 'Daily Logs' }).click();
  await expect(page.getByRole('heading', { name: 'Daily Logs', exact: true })).toBeVisible();
  await expect(page.getByText('Compiled by OG from 1 site update')).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'More' }).click();
  await page.getByRole('link', { name: 'Activity' }).click();
  await expect(page.getByRole('heading', { name: 'What OG has handled' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Cement shortage detected and sent for approval\./ })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(browserErrors).toEqual([]);
});
