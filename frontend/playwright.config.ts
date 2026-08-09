import { defineConfig, devices } from '@playwright/test';

const port = 3100;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chromium',
      use: {
        ...devices['Pixel 7'],
        launchOptions: {
          args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
        },
      },
    },
  ],
  webServer: [
    {
      command: '../.venv/bin/python ../scripts/run_e2e_api.py',
      url: 'http://127.0.0.1:8001/health/live',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'XDG_CONFIG_HOME=/tmp/oga-foreman-firebase firebase emulators:start --only auth --project oga-foreman-playwright --config ../firebase.json',
      url: 'http://127.0.0.1:9099/emulator/v1/projects/oga-foreman-playwright/config',
      reuseExistingServer: true,
      timeout: 90_000,
    },
    {
      command: `npm run build && npm run start -- --hostname 127.0.0.1 --port ${port}`,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        NEXT_DIST_DIR: '.next-playwright',
        NEXT_PUBLIC_DEMO_MODE: 'false',
        NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:8001',
        NEXT_PUBLIC_FIREBASE_API_KEY: 'playwright-api-key',
        NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'oga-foreman-playwright.firebaseapp.com',
        NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'oga-foreman-playwright',
        NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: 'oga-foreman-playwright.appspot.com',
        NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: '1234567890',
        NEXT_PUBLIC_FIREBASE_APP_ID: '1:1234567890:web:playwright',
        NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_URL: 'http://127.0.0.1:9099',
      },
    },
  ],
});
