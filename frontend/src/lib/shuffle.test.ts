import assert from "node:assert/strict";
import { test } from "node:test";
import { smartShuffle, weightFor } from "./shuffle.ts";
import type { Track } from "./types.ts";

function rngFrom(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let n = 0;
function track(artist: string, extra: Partial<Track> = {}): Track {
  n++;
  return {
    id: `t${n}`, title: `Song ${n}`, artist: { id: artist, name: artist }, album: null, genre: null, license: null,
    status: "ready", duration_ms: 200000, cover_url: null, error: null, created_at: "2026-01-01T00:00:00Z", ...extra,
  };
}

const plain = <T,>(items: T[], rng: () => number) => {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};

const adjacentSameArtist = (list: Track[]) => list.slice(1).filter((t, i) => t.artist.id === list[i].artist.id).length;

test("returns every track exactly once, even when one artist is the whole library", () => {
  const library = Array.from({ length: 12 }, () => track("A. R. Rahman"));
  const out = smartShuffle(library, null, { rng: rngFrom(1) });
  assert.equal(out.length, library.length);
  assert.deepEqual(new Set(out.map((t) => t.id)), new Set(library.map((t) => t.id)));
});

test("keeps the same artist from playing back to back far more often than a plain shuffle", () => {
  const library = ["Ilaiyaraaja", "Mano", "S. Janaki", "SPB"].flatMap((a) => Array.from({ length: 6 }, () => track(a)));
  let smart = 0, random = 0;
  for (let seed = 1; seed <= 200; seed++) {
    smart += adjacentSameArtist(smartShuffle(library, null, { rng: rngFrom(seed) }));
    random += adjacentSameArtist(plain(library, rngFrom(seed)));
  }
  assert.ok(smart < random * 0.5, `smart ${smart} vs plain ${random}`);
});

test("the same film is split up as well", () => {
  const film = (title: string) => ({ id: title, title });
  const a = track("X", { album: film("Roja") });
  const b = track("Y", { album: film("roja ") });
  const c = track("Z", { album: film("Bombay") });
  assert.ok(weightFor(b, a, null, {}) < weightFor(c, a, null, {}) / 3);
});

test("liked songs come earlier on average", () => {
  const library = Array.from({ length: 20 }, (_, i) => track(`artist${i}`));
  const liked = new Set(library.slice(0, 5).map((t) => t.id));
  let likedPos = 0, otherPos = 0;
  for (let seed = 1; seed <= 300; seed++) {
    smartShuffle(library, null, { liked, rng: rngFrom(seed) }).forEach((t, i) => (liked.has(t.id) ? (likedPos += i) : (otherPos += i)));
  }
  assert.ok(likedPos / (300 * 5) < otherPos / (300 * 15), "liked songs should sit nearer the front");
});

test("songs played in the last hours are pushed back, and recover as time passes", () => {
  const now = 1_000_000_000_000;
  const heard = track("A"), fresh = track("B");
  const just = new Map([[heard.id, now - 60_000]]);
  assert.ok(weightFor(heard, null, null, { recentlyPlayed: just, now }) < 0.4 * weightFor(fresh, null, null, { now }));
  const old = new Map([[heard.id, now - 7 * 3600_000]]);
  assert.equal(weightFor(heard, null, null, { recentlyPlayed: old, now }), 1);
});

test("flows between similar energy instead of jumping from soft to loud", () => {
  const soft = Array.from({ length: 8 }, (_, i) => track(`s${i}`, { energy: 0.03 + i * 0.001, tempo_bpm: 70 }));
  const loud = Array.from({ length: 8 }, (_, i) => track(`l${i}`, { energy: 0.3 + i * 0.01, tempo_bpm: 150 }));
  const library = [...soft, ...loud];
  const jumps = (list: Track[]) => list.slice(1).filter((t, i) => Math.abs(Math.log(t.energy! / list[i].energy!)) > 1).length;
  let smart = 0, random = 0;
  for (let seed = 1; seed <= 200; seed++) {
    smart += jumps(smartShuffle(library, null, { rng: rngFrom(seed) }));
    random += jumps(plain(library, rngFrom(seed)));
  }
  assert.ok(smart < random * 0.4, `smart ${smart} vs plain ${random}`);
});

test("half and double time count as the same tempo", () => {
  const slow = track("A", { tempo_bpm: 70, energy: 0.1 });
  const double = track("B", { tempo_bpm: 140, energy: 0.1 });
  const unrelated = track("C", { tempo_bpm: 100, energy: 0.1 });
  assert.ok(weightFor(double, slow, null, {}) > weightFor(unrelated, slow, null, {}));
});

test("tracks without analysis still shuffle normally", () => {
  const library = Array.from({ length: 6 }, (_, i) => track(`a${i}`));
  assert.equal(weightFor(library[1], library[0], null, {}), 1);
});
