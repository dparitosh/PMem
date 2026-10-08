import { defineConfig } from '@playwright/test';
import configuration from './playwright.config.js';

// Focused navigation checks use installed Chrome and mocked service responses.
export default defineConfig({
  ...configuration,
  testMatch: '**/page-navigation-smoke.e2e.spec.js',
  use: { baseURL: 'http://localhost:3000', screenshot: 'only-on-failure' },
  projects: [{ name: 'chrome-navigation', use: { channel: 'chrome' } }],
  webServer: {
    ...configuration.webServer,
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host localhost --port 3000 --strictPort`,
  },
});
