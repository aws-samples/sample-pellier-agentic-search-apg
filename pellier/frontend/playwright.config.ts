/**
 * Playwright config for the workshop / auth E2E suites.
 *
 * ``testDir`` is ``e2e/`` — Playwright specs live alongside the
 * frontend package so ``@playwright/test`` resolves from this
 * package's ``node_modules``. Frontend-level unit tests still live
 * in ``src/`` and run through Vitest, which has its own config block
 * in ``vite.config.ts``.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
