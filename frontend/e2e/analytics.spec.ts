import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Needs `ffmpeg` on the machine running the tests.
const run = Math.random().toString(36).slice(2, 10);
const A = `EvA${run}`;
const B = `EvB${run}`;
const user = `ev_${run}`;
const password = "correct horse battery";

function tone(dir: string, title: string, hz: number): string {
  const file = path.join(dir, `${title}.mp3`);
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", `sine=frequency=${hz}:duration=6`,
    "-metadata", `title=${title}`, "-metadata", "artist=Ev Test Band", file]);
  return file;
}

test.describe.configure({ mode: "serial" });

test("client fires play_start and a correctly-reasoned skip event", async ({ page }) => {
  const dir = mkdtempSync(path.join(tmpdir(), "listens-ev-e2e-"));
  const files = [tone(dir, A, 440), tone(dir, B, 660)];

  await page.goto("/register");
  await page.getByLabel("Email").fill(`${user}@example.com`);
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(password);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("whoami")).toHaveText(`@${user}`);

  await page.getByRole("link", { name: "Upload" }).first().click();
  await page.getByTestId("file-input").setInputFiles(files);
  await page.getByTestId("rights").check();
  await page.getByTestId("upload-submit").click();
  await expect(page.getByTestId("track-status")).toHaveText(["Ready", "Ready"], { timeout: 60_000 });

  // Track rows no longer link to the artist page (clicking anywhere on a row just plays it -
  // the artist page is reached through its own nav elsewhere), so fetch the artist id directly.
  const artistId: string = await page.evaluate(async () => {
    const r = await fetch("/api/catalogue/tracks/mine", { headers: { Authorization: `Bearer ${JSON.parse(localStorage.getItem("listens.auth")!).access}` } });
    return (await r.json())[0].artist.id;
  });
  await page.goto(`/artist/${artistId}`);
  await expect(page.getByTestId("page-title")).toHaveText("Ev Test Band");
  const rows = page.getByTestId("track-row");
  await expect(rows).toHaveCount(2);

  // The artist page lists newest-first, so play the FIRST row (not hardcoded to A or B) -
  // that's the only one of the two with a "next" track to skip to.
  const firstTitle = (await rows.first().getAttribute("data-title"))!;
  const secondTitle = (await rows.nth(1).getAttribute("data-title"))!;

  const playStart = page.waitForRequest(
    (r) => r.url().includes("/api/catalogue/events") && r.method() === "POST" && (r.postDataJSON()?.event_type === "play_start"),
  );
  await rows.first().getByRole("button", { name: `Play ${firstTitle}`, exact: true }).click();
  await expect(page.getByTestId("now-title")).toHaveText(firstTitle);
  const startReq = await playStart;
  expect(startReq.postDataJSON().track_id).toBeTruthy();

  // Accumulate a little real playback time before skipping - master/variant/segment all fetch
  // from Backblaze B2 now (a real network hop, not co-located MinIO), so give playback enough
  // time to actually start before asserting it advanced.
  await page.waitForTimeout(4000);

  // clicking Next must close out the first track as a "skip" with reason "next_button",
  // carrying its playback position
  const skipReq = page.waitForRequest(
    (r) => r.url().includes("/api/catalogue/events") && r.method() === "POST" && (r.postDataJSON()?.event_type === "skip"),
  );
  await expect(page.getByTestId("next")).toBeEnabled();
  await page.getByTestId("next").click();
  await expect(page.getByTestId("now-title")).toHaveText(secondTitle);
  const skip = (await skipReq).postDataJSON();
  expect(skip.reason).toBe("next_button");
  expect(skip.position_ms).toBeGreaterThan(0);
});

test("Profile's Listening stats and Recents render seeded play data", async ({ page, request }) => {
  const dir = mkdtempSync(path.join(tmpdir(), "listens-ev-e2e2-"));
  const u = `ev2_${run}`;
  const file = tone(dir, `AnalyticsTrack${run}`, 300);

  await page.goto("/register");
  await page.getByLabel("Email").fill(`${u}@example.com`);
  await page.getByLabel("Username").fill(u);
  await page.getByLabel("Password").fill(password);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("whoami")).toHaveText(`@${u}`);

  await page.getByRole("link", { name: "Upload" }).first().click();
  await page.getByTestId("file-input").setInputFiles(file);
  await page.getByTestId("rights").check();
  await page.getByTestId("upload-submit").click();
  await expect(page.getByTestId("track-status")).toHaveText(["Ready"], { timeout: 60_000 });

  // grab the access token straight from the page's own localStorage to call the API directly
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem("listens.auth") || "{}").access);
  const trackId: string = await page.evaluate(async () => {
    const r = await fetch("/api/catalogue/tracks/mine", { headers: { Authorization: `Bearer ${JSON.parse(localStorage.getItem("listens.auth")!).access}` } });
    return (await r.json())[0].id;
  });

  const headers = { Authorization: `Bearer ${token}` };
  await request.post("/api/catalogue/events", { headers, data: { event_type: "play_start", track_id: trackId } });
  await request.post("/api/catalogue/events", { headers, data: { event_type: "play_end", track_id: trackId, ms_played: 40_000 } });

  // give the events consumer a moment to drain the stream into Postgres
  await expect(async () => {
    const r = await request.get("/api/catalogue/analytics/recents", { headers });
    expect((await r.json()).length).toBeGreaterThan(0);
  }).toPass({ timeout: 10_000 });

  await page.getByRole("link", { name: "Profile" }).first().click();
  await page.getByRole("link", { name: "Listening stats" }).click();
  await expect(page.getByText(`AnalyticsTrack${run}`)).toBeVisible();

  await page.goBack();
  await page.getByRole("link", { name: "Recents" }).click();
  await expect(page.getByText("Today")).toBeVisible();
  await expect(page.getByText("1 song played")).toBeVisible();
});
