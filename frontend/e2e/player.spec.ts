import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Needs `ffmpeg` on the machine running the tests (to synthesise two tone files).
const run = Date.now().toString(36);
const A = `Alpha${run}`;
const B = `Beta${run}`;
const user = `e2e_${run}`;
const password = "correct horse battery";

function tone(dir: string, title: string, hz: number, seconds: number): string {
  const file = path.join(dir, `${title}.mp3`);
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", `sine=frequency=${hz}:duration=${seconds}`,
    "-b:a", "320k", "-metadata", `title=${title}`, "-metadata", "artist=E2E Band", "-metadata", "album=E2E Album", file]);
  return file;
}

const seconds = async (page: Page) => {
  const t = (await page.getByTestId("time-current").textContent()) ?? "0:00";
  const [m, s] = t.split(":").map(Number);
  return m * 60 + s;
};

test.describe.configure({ mode: "serial" });

test("register, upload, stream, control the player, search, persist", async ({ page }) => {
  const dir = mkdtempSync(path.join(tmpdir(), "listens-e2e-"));
  const files = [tone(dir, A, 440, 40), tone(dir, B, 660, 40)];

  // --- register through the UI -----------------------------------------------------------
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/); // unauthenticated -> login
  await page.getByRole("link", { name: "Register" }).click();
  await page.getByLabel("Email").fill(`${user}@example.com`);
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("whoami")).toHaveText(`@${user}`);

  // --- upload two tracks; wait for the background FFmpeg worker to mark them ready ------------
  await page.getByRole("link", { name: "Upload" }).first().click();
  await expect(page.getByTestId("upload-submit")).toBeDisabled(); // needs file + rights confirmation
  await page.getByTestId("file-input").setInputFiles(files);
  await page.getByTestId("rights").check();
  await page.getByTestId("upload-submit").click();
  const rows = page.getByTestId("track-row");
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId("track-status")).toHaveText(["Ready", "Ready"], { timeout: 90_000 });

  // --- play from Home ----------------------------------------------------------------------------
  await page.getByRole("link", { name: "Home" }).first().click();
  await expect(page.getByTestId("track-row")).toHaveCount(2);
  await expect(page.getByTestId("player-bar")).toHaveCount(0); // nothing playing yet
  await page.getByRole("button", { name: `Play ${A}`, exact: true }).click();
  await expect(page.getByTestId("now-title")).toHaveText(A);
  await expect.poll(() => seconds(page), { timeout: 20_000 }).toBeGreaterThanOrEqual(2); // audio is really advancing
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", false);
  await expect(page.getByTestId("player-error")).toHaveCount(0);

  // --- pause / resume -----------------------------------------------------------------------------
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", true);
  const frozen = await seconds(page);
  await page.waitForTimeout(1500);
  expect(await seconds(page)).toBe(frozen);
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", false);

  // --- seek ------------------------------------------------------------------------------------------
  await page.getByTestId("seek").fill("25");
  await expect.poll(() => seconds(page), { timeout: 15_000 }).toBeGreaterThanOrEqual(25);
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", false);

  // --- volume + quality switching ---------------------------------------------------------------------
  await page.getByTestId("volume").fill("0.3");
  await expect(page.getByTestId("audio")).toHaveJSProperty("volume", 0.3);
  const quality = page.getByTestId("quality-select");
  await expect(quality.locator("option")).toHaveText(["Auto", "96 kbps · data saver", "160 kbps · normal", "320 kbps · best"]);
  await quality.selectOption("96");
  const before = await seconds(page);
  await expect.poll(() => seconds(page), { timeout: 20_000 }).toBeGreaterThan(before); // keeps playing after the switch
  await quality.selectOption("auto");

  // --- queue ---------------------------------------------------------------------------------------------------
  // Clicking a row plays within that list (Home is newest-first): queue = [B, A], current = A.
  const queue = page.getByTestId("queue-item");
  await page.getByTestId("queue-toggle-desktop").click();
  await expect(queue).toHaveCount(2);
  await expect(queue.nth(0)).toHaveAttribute("data-current", "false");
  await expect(queue.nth(1)).toHaveAttribute("data-current", "true");
  await page.getByRole("button", { name: "Close queue" }).click();
  await expect(page.getByTestId("next")).toBeDisabled(); // A is last in the queue

  // Prefetch: once a next track exists, its signed URL + first segment are fetched ahead of time...
  let urlRequests = 0;
  page.on("request", (r) => /\/api\/stream\/tracks\/[^/]+\/url$/.test(r.url()) && urlRequests++);
  const prefetched = page.waitForResponse((r) => /\/api\/stream\/tracks\/[^/]+\/url$/.test(r.url()), { timeout: 15_000 });
  await page.getByRole("button", { name: `Add ${B} to queue` }).click(); // queue = [B, A, B]
  await prefetched;
  await page.waitForTimeout(1500); // let the playlist + first segment finish downloading
  await expect(page.getByTestId("next")).toBeEnabled();
  const requestsBefore = urlRequests;
  await page.getByTestId("next").click();
  await expect(page.getByTestId("now-title")).toHaveText(B);
  expect(urlRequests).toBe(requestsBefore); // ...so starting it needed no new URL request
  await expect(page.getByTestId("next")).toBeDisabled();
  await expect.poll(() => seconds(page), { timeout: 20_000 }).toBeGreaterThanOrEqual(4);

  // more than 3 s in -> "previous" restarts the same track instead of going back
  await page.getByTestId("prev").click();
  await expect(page.getByTestId("now-title")).toHaveText(B);
  await expect.poll(() => seconds(page)).toBeLessThanOrEqual(2);
  await page.getByTestId("prev").click(); // now < 3 s in -> go back one track
  await expect(page.getByTestId("now-title")).toHaveText(A);

  // jump to a queue entry
  await page.getByTestId("queue-toggle-desktop").click();
  await queue.nth(0).getByRole("button").first().click();
  await expect(page.getByTestId("now-title")).toHaveText(B);
  await expect(queue.nth(0)).toHaveAttribute("data-current", "true");
  await page.getByRole("button", { name: "Close queue" }).click();
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", false);

  // --- persistent mini-player across navigation ----------------------------------------------------------------
  const t0 = await seconds(page);
  await page.getByRole("link", { name: "Search" }).first().click();
  await expect(page).toHaveURL(/\/search/);
  await expect(page.getByTestId("now-title")).toHaveText(B); // same player instance, no reload
  await expect.poll(() => seconds(page), { timeout: 15_000 }).toBeGreaterThan(t0);
  await expect(page.getByTestId("audio")).toHaveJSProperty("paused", false);

  // --- search (prefix match, case-insensitive) -------------------------------------------------------------------
  await page.getByTestId("search-input").fill(B.slice(0, 8).toUpperCase());
  await expect(page.getByTestId("track-row")).toHaveCount(1);
  await expect(page.getByTestId("track-row")).toHaveAttribute("data-title", B);
  await page.getByTestId("search-input").fill("e2e ban"); // by artist name, two tokens
  await expect(page.getByTestId("track-row")).toHaveCount(2);
  await page.getByTestId("search-input").fill("zzzznothing");
  await expect(page.getByTestId("no-results")).toBeVisible();

  // --- session survives a reload, then sign out ------------------------------------------------------------------------
  await page.reload();
  await expect(page.getByTestId("whoami")).toHaveText(`@${user}`);
  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/upload");
  await expect(page).toHaveURL(/\/login$/); // protected again
});
