import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Needs `ffmpeg` on the machine running the tests.
// Random, not just Date.now(): see the comment in player.spec.ts for why.
const run = Math.random().toString(36).slice(2, 10);
const A = `LibA${run}`;
const B = `LibB${run}`;
const user = `lib_${run}`;
const password = "correct horse battery";

function tone(dir: string, title: string, hz: number): string {
  const file = path.join(dir, `${title}.mp3`);
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", `sine=frequency=${hz}:duration=5`,
    "-metadata", `title=${title}`, "-metadata", "artist=Lib Test Band", file]);
  return file;
}

test.describe.configure({ mode: "serial" });

test("playlists, likes, follow, and lyrics", async ({ page }) => {
  const dir = mkdtempSync(path.join(tmpdir(), "listens-lib-e2e-"));
  const files = [tone(dir, A, 440), tone(dir, B, 660)];

  await page.goto("/register");
  await page.getByLabel("Email").fill(`${user}@example.com`);
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("whoami")).toHaveText(`@${user}`);

  // --- upload two tracks and wait for them to be ready ----------------------------------------
  await page.getByRole("link", { name: "Upload" }).first().click();
  await page.getByTestId("file-input").setInputFiles(files);
  await page.getByTestId("rights").check();
  await page.getByTestId("upload-submit").click();
  await expect(page.getByTestId("track-status")).toHaveText(["Ready", "Ready"], { timeout: 60_000 });

  // --- likes: toggle from Home, verify it persists across reload ------------------------------
  // The track can legitimately appear in both "New uploads" and "Made for you" (its fallback
  // for a fresh user), so scope to one section rather than track-row text alone.
  await page.getByRole("link", { name: "Home" }).first().click();
  const newUploads = page.getByRole("region", { name: "New uploads" });
  const rowA = newUploads.getByTestId("track-row").filter({ has: page.getByText(A, { exact: true }) });
  await rowA.getByTestId("like-toggle").click();
  await expect(rowA.getByTestId("like-toggle")).toHaveAttribute("data-liked", "true");
  await page.reload();
  const rowAAfterReload = page.getByRole("region", { name: "New uploads" })
    .getByTestId("track-row").filter({ has: page.getByText(A, { exact: true }) });
  await expect(rowAAfterReload.getByTestId("like-toggle")).toHaveAttribute("data-liked", "true");

  // --- playlists: create, add a track, reorder, rename ------------------------------------------
  await page.getByRole("link", { name: "Playlists" }).first().click();
  await page.getByTestId("new-playlist-toggle").click();
  await page.getByTestId("new-playlist-name").fill("E2E Mix");
  await page.getByTestId("new-playlist-submit").click();
  await expect(page.getByTestId("playlist-card")).toHaveCount(1);
  await page.getByTestId("playlist-card").click();
  await expect(page.getByTestId("page-title")).toHaveText("E2E Mix");

  // add both tracks to the playlist from Home (scoped to "New uploads": a track can also
  // legitimately appear in "Made for you") via the add-to-playlist menu
  await page.getByRole("link", { name: "Home" }).first().click();
  const newUploadsSection = page.getByRole("region", { name: "New uploads" });
  for (const title of [A, B]) {
    const row = newUploadsSection.getByTestId("track-row").filter({ has: page.getByText(title, { exact: true }) });
    await row.getByTestId("add-to-playlist").click();
    await page.getByTestId("add-to-playlist-option").filter({ hasText: "E2E Mix" }).click();
    await expect(page.getByTestId("add-to-playlist-menu")).toHaveCount(0, { timeout: 3000 });
  }

  await page.getByRole("link", { name: "Playlists" }).first().click();
  await page.getByTestId("playlist-card").click();
  await expect(page.getByTestId("playlist-track-row")).toHaveCount(2);
  // order of insertion was A, B -> expect A first
  await expect(page.getByTestId("playlist-track-row").first()).toHaveAttribute("data-title", A);

  // move the second row (B) up: expect B, A
  await page.getByTestId("playlist-track-row").nth(1).getByTestId("move-up").click();
  await expect(page.getByTestId("playlist-track-row").first()).toHaveAttribute("data-title", B);

  // rename
  await page.getByTestId("playlist-rename-toggle").click();
  await page.getByTestId("playlist-rename-input").fill("E2E Mix Renamed");
  await page.getByTestId("playlist-rename-save").click();
  await expect(page.getByTestId("page-title")).toHaveText("E2E Mix Renamed");

  // remove a track
  await page.getByTestId("playlist-track-row").first().getByTestId("remove-from-playlist").click();
  await expect(page.getByTestId("playlist-track-row")).toHaveCount(1);

  // --- follow an artist ------------------------------------------------------------------------
  await page.getByTestId("playlist-track-row").first().getByText("Lib Test Band").click();
  await expect(page.getByTestId("page-title")).toHaveText("Lib Test Band");
  await expect(page.getByTestId("follow-toggle")).toHaveAttribute("data-followed", "false");
  await page.getByTestId("follow-toggle").click();
  await expect(page.getByTestId("follow-toggle")).toHaveAttribute("data-followed", "true");
  await expect(page.getByTestId("follow-toggle")).toHaveText("Following");

  // --- lyrics panel: no lyrics on a synthetic tone, but the panel must open and say so clearly ---
  await page.getByRole("button", { name: `Play ${B}`, exact: true }).click();
  await expect(page.getByTestId("now-title")).toHaveText(B);
  await page.getByTestId("lyrics-toggle-desktop").click();
  await expect(page.getByTestId("lyrics-panel")).toBeVisible();
  await expect(page.getByTestId("lyrics-empty")).toHaveText("No lyrics available for this track.");

  // --- delete the playlist (owner only) ----------------------------------------------------------
  await page.getByRole("link", { name: "Playlists" }).first().click();
  await page.getByTestId("playlist-card").click();
  await page.on("dialog", (d) => d.accept());
  await page.getByTestId("delete-playlist").click();
  await expect(page).toHaveURL(/\/playlists$/);
  await expect(page.getByTestId("playlist-list")).toHaveCount(0);
});
