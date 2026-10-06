import { defineConfig } from "@playwright/test";

// Runs against a live stack (docker compose up) through the gateway.
//   E2E_BASE_URL=http://localhost:8080 npx playwright test
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.E2E_CHROMIUM_PATH || undefined,
      args: ["--autoplay-policy=no-user-gesture-required"],
    },
  },
});
