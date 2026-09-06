import { defineConfig } from "@playwright/test";

/**
 * The browser walk-through.
 *
 * Everything else in this repository tests the application through its API or
 * through a rendered component. This drives the real pages in a real browser:
 * a person's keystrokes, against a backend of its own so a failed run cannot
 * touch the production database.
 *
 * The backend it talks to must be started first, on 8011, with mock providers
 * and its own data directory - see e2e/README.md. Chrome is used as installed
 * rather than downloaded, because the Playwright browser download is blocked
 * on this machine.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5233",
    channel: "chrome",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5233 --strictPort",
    url: "http://localhost:5233",
    reuseExistingServer: false,
    timeout: 60_000,
    env: { CAS_API_URL: "http://127.0.0.1:8011" },
  },
});
