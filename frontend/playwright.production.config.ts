import { defineConfig } from "@playwright/test";

/**
 * Producing a real episode by typing it in.
 *
 * Not a test. This drives the running application against the real backend on
 * 8001 - the live database, the live ComfyUI - the way a creator would, and
 * leaves a real project behind. It is kept apart from `playwright.config.ts`
 * for that reason: the walk-through there is disposable and this is not.
 *
 * The dev server and backend must already be running. Nothing here starts or
 * stops them.
 */
export default defineConfig({
  testDir: "./e2e-production",
  // Real generation is minutes per clip, and the page is polled while it runs.
  timeout: 45 * 60_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    channel: "chrome",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    actionTimeout: 60_000,
  },
});
