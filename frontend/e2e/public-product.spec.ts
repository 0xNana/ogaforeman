import { expect, test, type Page } from '@playwright/test';

function captureBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  return errors;
}

test('opens the deterministic product demo from the landing page', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);

  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: /Your site doesn.t need another dashboard/i }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'See Oga in action' }).first().click();

  await expect(page).toHaveURL(/\/demo$/);
  await expect(
    page.getByRole('heading', { name: 'One update. The follow-through handled.' }),
  ).toBeVisible();
  await expect(
    page.getByLabel('Interactive Oga product demonstration'),
  ).toContainText('First-floor blockwork is done.');
  await expect(page.getByText('Approve cement request · 100 bags')).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('renders a keyboard-usable sign-up form', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page);

  await page.goto('/sign-up');
  await expect(page.getByRole('heading', { name: 'Start with one site update.' })).toBeVisible();

  await page.getByLabel('Full name').fill('Ama Mensah');
  await page.getByLabel('Email').fill('ama@example.test');
  await page.getByLabel('Password').fill('safe-password');

  await expect(page.getByRole('button', { name: /Create account/ })).toBeEnabled();
  await page.getByLabel('Full name').focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Email')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Password')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: /Create account/ })).toBeFocused();
  await expect(page.getByRole('link', { name: /See Oga in action without signing in/ })).toBeVisible();
  expect(browserErrors).toEqual([]);
});
