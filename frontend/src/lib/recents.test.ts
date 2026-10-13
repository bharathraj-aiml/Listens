import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeRecents, type LocalRecent } from "./recents.ts";
import type { Track } from "./types.ts";

let n = 0;
const track = (title: string, extra: Partial<Track> = {}): Track => ({
  id: "t" + ++n, title, artist: { id: "a", name: "A" }, album: null, genre: null, license: null, status: "ready",
  duration_ms: 1000, cover_url: null, error: null, created_at: "2026-01-01T00:00:00Z", ...extra,
});
const at = (iso: string) => Date.parse(iso);
const titles = (xs: Track[]) => xs.map((t) => t.title);

test("a song you just played on this device appears first, before any refetch", () => {
  const old = track("Old", { played_at: "2026-10-12T01:00:00Z" });
  const fresh = track("Fresh");
  assert.deepEqual(titles(mergeRecents([old], [{ track: fresh, at: at("2026-10-12T02:00:00Z") }])), ["Fresh", "Old"]);
});

test("each song appears once, at its newest time, from whichever side knows it", () => {
  const a = track("A", { played_at: "2026-10-12T01:00:00Z" });
  const b = track("B", { played_at: "2026-10-12T03:00:00Z" });
  const local: LocalRecent[] = [{ track: a, at: at("2026-10-12T02:00:00Z") }];
  assert.deepEqual(titles(mergeRecents([a, b], local)), ["B", "A"]); // b is newer on the server; a's local time beats its server time
  assert.equal(mergeRecents([a, b], local).length, 2);
});

test("plays from another device (server only) are ordered by their real time", () => {
  const phone = track("On phone", { played_at: "2026-10-12T05:00:00Z" });
  const here = track("Here", { played_at: "2026-10-12T04:00:00Z" });
  assert.deepEqual(titles(mergeRecents([here, phone], [])), ["On phone", "Here"]);
});

test("server songs without a time keep the server's order, after anything with a time", () => {
  const timed = track("Timed", { played_at: "2026-10-12T01:00:00Z" });
  const x = track("X"), y = track("Y");
  assert.deepEqual(titles(mergeRecents([x, y, timed], [])), ["Timed", "X", "Y"]);
});

test("songs that are not ready are never shown, and the list is capped", () => {
  const failed = track("Failed", { status: "failed" });
  const many = Array.from({ length: 30 }, (_, i) => track("S" + i, { played_at: new Date(Date.UTC(2026, 9, 12, 0, i)).toISOString() }));
  const out = mergeRecents([failed, ...many], [], 20);
  assert.equal(out.length, 20);
  assert.ok(!titles(out).includes("Failed"));
  assert.equal(out[0].title, "S29");
});

test("on a tie the song is shown once, using the server's copy (its cover link is always current)", () => {
  const server = track("Same", { played_at: "2026-10-12T01:00:00Z", cover_url: "server-fresh" });
  const local = { ...server, cover_url: "device-old" };
  const merged = mergeRecents([server], [{ track: local, at: at("2026-10-12T01:00:00Z") }]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].cover_url, "server-fresh");
});

test("a song stored on the device keeps this device's time but takes the server's fresh copy (its cover link has not expired)", () => {
  const stale = { ...track("A"), cover_url: "/cover/old-expired-token" };
  const fresh = { ...track("A"), id: stale.id, cover_url: "/cover/new-token", played_at: new Date(1000).toISOString() };
  const merged = mergeRecents([fresh], [{ track: stale, at: 5000 }]);
  assert.deepEqual(merged.map((x) => x.cover_url), ["/cover/new-token"]);
});
