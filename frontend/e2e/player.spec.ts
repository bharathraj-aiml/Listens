import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Needs `ffmpeg` on the machine running the tests (to synthesise two tone files).
// Random, not just Date.now(): a base36 timestamp's leading (most significant) digits barely
// change over a few minutes, so slicing a prefix of a title built from one alone can collide
// across repeated runs against the same un-reset dev stack. Random digits stay unique throughout.
const run = Math.random().toString(36).slice(2, 10);
const A = `Alpha${run}`;
const B = `Beta${run}`;
const user = `e2e_${run}`;
const password = "correct horse battery";

function tone(dir: string, title: string, hz: number, seconds: number): string {
  const file = path.join(dir, `${title}.mp3`);
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", `sine=frequency=${hz}:duration=${seconds}`,
    "-b:a", "320k", "-metadata", `title=${title}`, "-metadata", `artist=E2E Band ${run}`, "-metadata", "album=E2E Album", file]);
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
  // Uploads happen one at a time (see upload/page.tsx), each a real PUT to Backblaze B2 - allow
  // enough wall-clock time for both sequential uploads to complete over a real network hop.
  await expect(rows).toHaveCount(2, { timeout: 60_000 });
  await expect(page.getByTestId("track-status")).toHaveText(["Ready", "Ready"], { timeout: 90_000 });

  // --- play from the artist page -------------------------------------------------------------------
  // Home's "New uploads" is a global feed (every user's ready tracks, not just this run's), and
  // clicking Play there queues *everything visible in that list* - which grows as other e2e
  // specs upload in the same session, making an exact queue size unpredictable from Home. The
  // artist page is naturally bounded to exactly these 2 tracks instead: each test run registers
  // a fresh user, and artists are deduped per-uploader, so "E2E Band" here is this run's own,
  // private artist row with nothing else attached to it.
  await page.getByRole("link", { name: "Home" }).first().click();
  const newUploads = page.getByRole("region", { name: "New uploads" });
  await expect(newUploads.getByTestId("track-row").filter({ hasText: A })).toHaveCount(1);
  await expect(newUploads.getByTestId("track-row").filter({ hasText: B })).toHaveCount(1);
  await expect(page.getByTestId("player-bar")).toHaveCount(0); // nothing playing yet
  // Track rows no longer link to the artist page (clicking anywhere on a row just plays it -
  // the artist page is reached through its own nav elsewhere), so fetch the artist id directly.
  const artistId: string = await page.evaluate(async () => {
    const r = await fetch("/api/catalogue/tracks/mine", { headers: { Authorization: `Bearer ${JSON.parse(localStorage.getItem("listens.auth")!).access}` } });
    return (await r.json())[0].artist.id;
  });
  await page.goto(`/artist/${artistId}`);
  await expect(page.getByTestId("page-title")).toHaveText(`E2E Band ${run}`);
  await expect(page.getByTestId("track-row")).toHaveCount(2); // exactly this run's two tracks
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
  // (still on the artist page: bounded to exactly A and B, so this label is unique here)
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

  // --- similar tracks (Phase 5) ---------------------------------------------------------------------------------
  // Neither A nor B has an ALS vector yet (no play history old enough to train on), so this exercises
  // the cold-start fallback (tempo/energy proximity, or same-artist/genre). The dev stack's Postgres
  // volume accumulates "ready" tracks with audio features across every past test run, so this can't
  // assert an exact fallback tier or count - only that the panel works and never shows the track
  // it was opened from.
  await page.getByTestId("similar-toggle-desktop").click();
  const similarPanel = page.getByTestId("similar-panel");
  await expect(similarPanel).toBeVisible();
  const similarRows = similarPanel.getByTestId("track-row");
  await expect(similarRows.first()).toBeVisible({ timeout: 15_000 });
  expect(await similarRows.count()).toBeGreaterThan(0);
  await expect(similarRows.filter({ hasText: B })).toHaveCount(0); // never recommends the track itself
  await page.getByRole("button", { name: "Close similar tracks" }).click();
  await expect(similarPanel).toHaveCount(0);

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
  // Two tokens, by artist name; the run id is folded into the artist name (not just "e2e ban")
  // so this stays scoped to this run's own tracks even when the suite is re-run without a
  // database reset in between (other runs' tracks share the "E2E Band" name but not the suffix).
  await page.getByTestId("search-input").fill(`ban ${run}`);
  await expect(page.getByTestId("track-row")).toHaveCount(2);
  await page.getByTestId("search-input").fill("zzzznothing");
  await expect(page.getByTestId("no-results")).toBeVisible();

  // --- session survives a reload, then sign out (Profile -> Settings -> Log out) ------------------------
  await page.reload();
  await expect(page.getByTestId("whoami")).toHaveText(`@${user}`);
  await page.getByRole("link", { name: "Profile" }).first().click();
  await page.getByRole("link", { name: "Settings and privacy" }).click();
  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/upload");
  await expect(page).toHaveURL(/\/login$/); // protected again
});
