import { expect, test } from '@playwright/test';

import { captureBrowserErrors, projectId, signInToProject } from './support';

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Site intake evidence runs on mobile.');
  await signInToProject(page, testInfo);
  await page.goto(`/projects/${projectId}/site`);
  await expect(page.getByRole('heading', { name: 'Tell Oga what happened.' })).toBeVisible();
});

test('submits a text update through processing to durable completion', async ({ page, request }) => {
  const browserErrors = captureBrowserErrors(page);
  const siteRequest = page.waitForRequest((candidate) => (
    candidate.method() === 'POST' && candidate.url().endsWith('/site-updates')
  ));

  await page.getByLabel('Type a site update').fill('First-floor plastering is complete.');
  await page.getByRole('button', { name: 'Send to Oga' }).click();
  await expect(page.getByRole('status')).toContainText('Checking the project');
  const acceptedRequest = await siteRequest;
  const acceptedResponse = await acceptedRequest.response();
  const accepted = await acceptedResponse?.json();

  await expect(page.getByText('Oga handled it.')).toBeVisible();
  const run = await request.get(`http://127.0.0.1:8001${accepted.status_url}`, {
    headers: { Authorization: 'Bearer local-e2e-token' },
  });
  expect(run.ok()).toBe(true);
  expect((await run.json()).status).toBe('completed');
  expect(browserErrors).toEqual([]);
});

test('uploads and submits a photo using the signed attachment contract', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  await page.locator('#site-attachment').setInputFiles({
    name: 'site-progress.png',
    mimeType: 'image/png',
    buffer: Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex'),
  });
  await expect(page.getByText('site-progress.png')).toBeVisible();
  const siteRequest = page.waitForRequest((candidate) => (
    candidate.method() === 'POST' && candidate.url().endsWith('/site-updates')
  ));

  await page.getByRole('button', { name: 'Send to Oga' }).click();
  await expect(page.getByText('Adding your site photos...')).toBeVisible();
  const payload = JSON.parse((await siteRequest).postData() ?? '{}');

  expect(payload.input_type).toBe('photo');
  expect(payload.attachment_ids).toHaveLength(1);
  await expect(page.getByText('Oga handled it.')).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('records and submits a voice update', async ({ context, page }) => {
  await context.grantPermissions(['microphone'], { origin: 'http://127.0.0.1:3100' });
  const browserErrors = captureBrowserErrors(page);

  await page.getByRole('button', { name: 'Start voice recording' }).click();
  await expect(page.getByText('Listening...')).toBeVisible();
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: 'Stop recording' }).click();
  await expect(page.locator('.recorded-actions').getByText('Voice note ready')).toBeVisible();
  const siteRequest = page.waitForRequest((candidate) => (
    candidate.method() === 'POST' && candidate.url().endsWith('/site-updates')
  ));

  await page.getByRole('button', { name: 'Send to Oga' }).click();
  const payload = JSON.parse((await siteRequest).postData() ?? '{}');

  expect(payload.input_type).toBe('voice');
  expect(payload.attachment_ids).toHaveLength(1);
  await expect(page.getByText('Oga handled it.')).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('explains microphone denial without losing typed-input recovery', async ({ context, page }) => {
  await context.clearPermissions();
  await page.evaluate(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException('Permission denied', 'NotAllowedError');
    };
  });
  const browserErrors = captureBrowserErrors(page);

  await page.getByRole('button', { name: 'Start voice recording' }).click();

  await expect(page.locator('.status-banner[role="alert"]')).toContainText('Microphone access was denied');
  await expect(page.getByLabel('Type a site update')).toBeEnabled();
  expect(browserErrors).toEqual([]);
});

test('rejects an invalid attachment before creating a site update', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);
  let submitted = false;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/site-updates')) submitted = true;
  });
  await page.locator('#site-attachment').setInputFiles({
    name: 'unsafe.html',
    mimeType: 'text/html',
    buffer: Buffer.from('<script>alert(1)</script>'),
  });

  await page.getByRole('button', { name: 'Send to Oga' }).click();

  await expect(page.locator('.status-banner[role="alert"]')).toContainText('Use a photo, audio note or PDF.');
  expect(submitted).toBe(false);
  expect(browserErrors).toEqual([]);
});

test('renders durable clarification and processing failure states', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);

  await page.getByLabel('Type a site update').fill('It is nearly done.');
  await page.getByRole('button', { name: 'Send to Oga' }).click();
  await expect(page.getByRole('status')).toContainText('needs a clearer detail');

  await page.getByLabel('Type a site update').fill('Trigger a processing error.');
  await page.getByRole('button', { name: 'Send to Oga' }).click();
  await expect(page.locator('.status-banner[role="alert"]')).toContainText('could not be processed');
  expect(browserErrors).toEqual([]);
});
