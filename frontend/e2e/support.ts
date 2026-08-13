import { randomUUID } from 'node:crypto';
import { expect, type Page, type TestInfo } from '@playwright/test';

export const projectId = 'prj_playwright123';

export function captureBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  return errors;
}

export async function signInToProject(page: Page, testInfo: TestInfo): Promise<void> {
  const email = `${testInfo.project.name}-${randomUUID()}@example.test`;
  await page.goto(`/sign-up?next=/projects/${projectId}`);
  await page.getByLabel('Full name').fill('Ama Manager');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('local-e2e-password');
  await page.getByRole('button', { name: /Create account/ }).click();
  await expect.poll(
    () => new URL(page.url()).pathname,
    { timeout: 15_000 },
  ).toBe(`/projects/${projectId}`);
  await expect(
    testInfo.project.name === 'mobile-chromium'
      ? page.getByRole('heading', { name: 'Ridge House' })
      : page.getByRole('heading', { name: 'Project overview' }),
  ).toBeVisible({ timeout: 15_000 });
}
