import { defineConfig, type BrowserChannel } from "@playwright/test";

// Runs against a live stack (docker compose up) through the gateway.
//   E2E_BASE_URL=http://localhost:8080 npx playwright test
//
// Playwright's bundled Chromium ships without an AAC decoder (open-source build), so with the
// stack's default HLS_AUDIO_CODEC=aac, playback assertions will fail there (confirmed: it can
// play audio/mpeg but not audio/mp4;codecs="mp4a.40.2"). Two ways to actually test AAC:
//   E2E_BROWSER_CHANNEL=msedge npx playwright test   (uses the real, codec-complete system Edge)
// ...or set HLS_AUDIO_CODEC=mp3 in .env and use the bundled Chromium as-is.
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
    channel: (process.env.E2E_BROWSER_CHANNEL as BrowserChannel) || undefined,
    launchOptions: {
      args: ["--autoplay-policy=no-user-gesture-required"],
    },
  },
});
