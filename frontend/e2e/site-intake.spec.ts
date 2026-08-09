import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';

import { captureBrowserErrors, projectId, signInToProject } from './support';

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-chromium', 'Site intake evidence runs on mobile.');
  await signInToProject(page, testInfo);
  await page.goto(`/projects/${projectId}/site`);
  await expect(page.getByRole('heading', { name: 'Tell Oga what happened.' })).toBeVisible();
});

test('runs a site update through real approval and same-run continuation', async ({ page, request }) => {
  const browserErrors = captureBrowserErrors(page);
  const siteRequest = page.waitForRequest((candidate) => (
    candidate.method() === 'POST' && candidate.url().endsWith('/site-updates')
  ));

  await page.getByLabel('Type a site update').fill(
    'First-floor blockwork is complete. The electrician did not come today. '
      + 'We have 10 bags of cement left. Plastering starts tomorrow.',
  );
  await page.getByRole('button', { name: 'Send to Oga' }).click();
  await expect(page.getByRole('status')).toContainText('Checking the project');
  const acceptedRequest = await siteRequest;
  const acceptedResponse = await acceptedRequest.response();
  const accepted = await acceptedResponse?.json();

  expect(accepted).toBeTruthy();
  await expect(page.getByRole('heading', { name: 'Oga understood the update.' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('One decision is waiting for a manager');
  const pausedRun = await request.get(`http://127.0.0.1:8001${accepted.status_url}`, {
    headers: { Authorization: 'Bearer local-e2e-token' },
  });
  expect(pausedRun.ok()).toBe(true);
  expect((await pausedRun.json()).status).toBe('waiting_for_approval');

  await page.getByRole('link', { name: 'Review approval' }).click();
  const purchaseCard = page.getByRole('article').filter({ hasText: /30(?:\.0)? bags/ });
  await expect(purchaseCard.getByText('PENDING')).toBeVisible();
  await purchaseCard.getByRole('button', { name: 'Approve' }).click();
  await expect(purchaseCard.getByText('APPROVED')).toBeVisible();
  await expect(purchaseCard.getByRole('status')).toContainText(
    'Oga is resuming from the saved checkpoint.',
  );

  await expect.poll(async () => {
    const response = await request.get(`http://127.0.0.1:8001${accepted.status_url}`, {
      headers: { Authorization: 'Bearer local-e2e-token' },
    });
    return (await response.json()).status;
  }).toBe('completed');
  await purchaseCard.getByRole('link', { name: 'Follow in activity' }).click();
  await expect(page.getByRole('heading', {
    name: 'Submitted an approved material request to the supplier simulator.',
  })).toBeVisible();
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
  await expect(page.getByRole('status')).toContainText('needs a clearer detail');
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

test('persists a recoverable processing failure without a phrase trigger', async ({ page, request }) => {
  const browserErrors = captureBrowserErrors(page);
  await page.locator('#site-attachment').setInputFiles({
    name: 'site-note.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\n%%EOF\n'),
  });
  const siteRequest = page.waitForRequest((candidate) => (
    candidate.method() === 'POST' && candidate.url().endsWith('/site-updates')
  ));
  await page.getByRole('button', { name: 'Send to Oga' }).click();
  const submitted = await siteRequest;
  const response = await submitted.response();
  expect(response?.status()).toBe(503);
  await expect(page.locator('.status-banner[role="alert"]')).toContainText('Retry safely');

  const idempotencyKey = submitted.headers()['idempotency-key'];
  const updateDigest = createHash('sha256')
    .update(`${projectId}\0usr_playwright123\0${idempotencyKey}`)
    .digest('hex')
    .slice(0, 32);
  const eventId = `evt_${updateDigest}`;
  const runId = `run_${createHash('sha256').update(eventId).digest('hex').slice(0, 32)}`;
  const run = await request.get(
    `http://127.0.0.1:8001/api/v1/projects/${projectId}/agent-runs/${runId}`,
    { headers: { Authorization: 'Bearer local-e2e-token' } },
  );
  expect(run.ok()).toBe(true);
  expect((await run.json()).status).toBe('failed');
  expect(browserErrors.filter((message) => !message.includes('503 (Service Unavailable)'))).toEqual([]);
});
