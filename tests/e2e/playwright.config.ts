import { defineConfig } from "@playwright/test";

// E2E happy-path against the MOCKED backend + Vite dev server.
// Run: (1) from repo tender-bidding/: seed + start backend on :8014
//      (2) from tender-bidding/ui: npm run dev (:5174, proxies /api -> :8014)
//      (3) npx playwright test -c tests/e2e/playwright.config.ts
// The webServer below starts the Vite dev server; the backend must be running.
export default defineConfig({
  testDir: ".",
  timeout: 30_000,
  use: { baseURL: "http://localhost:5174", trace: "on-first-retry" },
  webServer: {
    command: "npm --prefix ui run dev",
    url: "http://localhost:5174",
    reuseExistingServer: true,
    timeout: 60_000,
    cwd: "..",
  },
});
