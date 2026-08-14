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
  await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'Electrical work is blocked by the absent electrician.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Issues' })).toBeVisible();
  const activityAccessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(activityAccessibility.violations).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test('conversation proposal survives refresh and confirms through the server contract', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop evidence runs in Chromium desktop.');
  let pending: Record<string, unknown> | null = null;
  const proposal = {
    proposal_id: 'cpr_browsergolden',
    kind: 'schedule',
    project_id: 'prj_ridge_house',
    actor_id: 'usr_manager',
    policy_decision: { policy: 'confirm_first', reason_code: 'consequential_reversible_change', use_existing_approval: false },
    idempotency_key: 'conversation:browser:golden',
    requested_action: 'Move plastering to Friday',
    observed_memory_version: 0,
    observed_entity_versions: { tsk_plastering: 7 },
    created_at: '2026-08-14T10:00:00Z',
    expires_at: '2026-08-14T10:15:00Z',
    signature: 'a'.repeat(64),
    command: {},
  };
  await page.route('**/conversations/proposals/pending', async (route) => {
    await route.fulfill({ json: { proposal: pending, memory_version: pending ? 1 : 0 } });
  });
  await page.route('**/conversations/messages', async (route) => {
    pending = proposal;
    await route.fulfill({
      json: {
        kind: 'proposed_change', text: 'That affects one downstream activity.', cited_record_ids: [],
        mutation_performed: false, proposed_action: 'Move plastering to Friday', proposal_id: proposal.proposal_id,
        memory_version: 1, proposal,
      },
    });
  });
  await page.route('**/conversations/proposals/cpr_browsergolden/confirm', async (route) => {
    const request = route.request();
    expect(request.postDataJSON()).toEqual({ observed_memory_version: 1 });
    pending = null;
    await route.fulfill({ json: { kind: 'done', text: 'Schedule updated.', cited_record_ids: [], mutation_performed: true } });
  });

  await signInToProject(page, testInfo);
  await page.getByRole('button', { name: 'Ask OG' }).click();
  let drawer = page.getByRole('dialog', { name: 'Ask OG' });
  await drawer.getByRole('textbox', { name: 'Message OG' }).fill('move plastering to Friday');
  await drawer.getByRole('button', { name: 'Send message' }).click();
  await expect(drawer.getByRole('button', { name: 'Confirm' })).toBeVisible();

  await page.reload();
  await page.getByRole('button', { name: 'Ask OG' }).click();
  drawer = page.getByRole('dialog', { name: 'Ask OG' });
  await expect(drawer.getByRole('heading', { name: 'Move plastering to Friday' })).toBeVisible();
  await drawer.getByRole('button', { name: 'Confirm' }).click();
  await expect(drawer.getByText('Schedule updated.')).toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Confirm' })).toHaveCount(0);
});

test('mobile command center navigation remains usable without overflow', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Mobile evidence runs with the Pixel viewport.');
  const browserErrors = captureBrowserErrors(page);

  await signInToProject(page, testInfo);
  await expect(page.getByRole('navigation', { name: 'Mobile project navigation' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ridge House' })).toBeVisible();
  await expect(page.getByText(/things need attention/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Talk to OG/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add site photos' })).toBeVisible();
  const fieldAccessibility = await new AxeBuilder({ page }).include('.mobile-field-home').withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(fieldAccessibility.violations).toEqual([]);
  await page.getByRole('button', { name: /Talk to OG/ }).click();
  const ogSheet = page.getByRole('dialog', { name: 'Ask OG' });
  await expect(ogSheet).toBeVisible();
  await expect.poll(async () => ogSheet.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return box.left === 0 && box.width === window.innerWidth && box.height === window.innerHeight;
  })).toBe(true);
  await expect(ogSheet.getByRole('button', { name: 'Add attachment' })).toBeVisible();
  await expect(ogSheet.getByRole('button', { name: 'Start voice recording' })).toBeVisible();
  await ogSheet.getByRole('button', { name: 'Close Ask OG' }).click();
  await page.getByRole('link', { name: 'Tasks', exact: true }).click();
  await page.getByRole('button', { name: 'Electrical rough-in' }).click();
  await expect(page.getByRole('dialog', { name: 'Electrical rough-in' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Close details' }).click();
  await page.getByRole('button', { name: 'More' }).click();
  const moreSheet = page.getByRole('dialog', { name: 'More sections' });
  await expect(moreSheet).toBeVisible();
  await expect(moreSheet.getByRole('button', { name: 'Close more sections' })).toBeFocused();
  const moreAccessibility = await new AxeBuilder({ page }).include('.mobile-more-sheet').withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(moreAccessibility.violations).toEqual([]);
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
  await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'Cement shortage detected and sent for approval.' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(browserErrors).toEqual([]);
});
