import type { Track } from "./types";

/** Smart shuffle: random, but not blind. Each next song is drawn (weighted, so it never feels
 *  scripted) from what is left, where a song's weight is:
 *
 *   taste     liked songs are drawn 1.6x as often
 *   freshness a song played in the last 6 hours is drawn less, recovering as time passes, so a
 *             re-shuffle does not open with what you just heard
 *   variety   the same artist as the song before is ~12x less likely, as the one before that 2x
 *             less; the same film (album title) back to back 4x less. A film soundtrack usually
 *             lists its songs together, which is exactly what a shuffle should break up
 *   flow      the closer a song's energy and tempo are to the song before, the likelier it is, so
 *             a soft melody is not followed by a loud beat-heavy number. Tempo counts half/double
 *             time as a match. Skipped when the analysis is missing, so unanalysed songs are
 *             simply drawn on the other three.
 *
 * Nothing is excluded outright, so any song can still come next; it is a bias, not a rule. */

const LIKED_BOOST = 1.6;
const FRESH_WINDOW_MS = 6 * 60 * 60 * 1000;
const SAME_ARTIST_AS_PREV = 0.08;
const SAME_ARTIST_AS_PREV2 = 0.5;
const SAME_ALBUM_AS_PREV = 0.25;
const FLOW_STRENGTH = 1.6;

export interface ShuffleOptions {
  liked?: ReadonlySet<string>;
  /** track id -> when it last started playing (epoch ms) */
  recentlyPlayed?: ReadonlyMap<string, number>;
  rng?: () => number;
  now?: number;
}

function flowDistance(a: Track, b: Track): number | null {
  const parts: number[] = [];
  if (a.energy && b.energy) parts.push(Math.abs(Math.log(a.energy / b.energy)));
  if (a.tempo_bpm && b.tempo_bpm) {
    const r = Math.abs(Math.log2(a.tempo_bpm / b.tempo_bpm));
    parts.push(Math.min(r, Math.abs(r - 1)) * 2); // half/double time is a match
  }
  return parts.length ? parts.reduce((x, y) => x + y, 0) / parts.length : null;
}

const sameAlbum = (a: Track, b: Track) =>
  !!a.album && !!b.album && a.album.title.trim().toLowerCase() === b.album.title.trim().toLowerCase();

export function weightFor(candidate: Track, prev: Track | null, prev2: Track | null, o: ShuffleOptions): number {
  let w = 1;
  if (o.liked?.has(candidate.id)) w *= LIKED_BOOST;

  const playedAt = o.recentlyPlayed?.get(candidate.id);
  if (playedAt !== undefined) {
    const age = (o.now ?? Date.now()) - playedAt;
    if (age >= 0 && age < FRESH_WINDOW_MS) w *= 0.3 + 0.7 * (age / FRESH_WINDOW_MS);
  }

  if (prev) {
    if (candidate.artist.id === prev.artist.id) w *= SAME_ARTIST_AS_PREV;
    if (sameAlbum(candidate, prev)) w *= SAME_ALBUM_AS_PREV;
    const d = flowDistance(prev, candidate);
    if (d !== null) w *= Math.exp(-FLOW_STRENGTH * d);
  }
  if (prev2 && candidate.artist.id === prev2.artist.id) w *= SAME_ARTIST_AS_PREV2;
  return w;
}

/** Orders `tracks` (the upcoming part of a queue) for playback after `current`. */
export function smartShuffle(tracks: Track[], current: Track | null, options: ShuffleOptions = {}): Track[] {
  const rng = options.rng ?? Math.random;
  const pool = [...tracks];
  const out: Track[] = [];
  let prev = current;
  let prev2: Track | null = null;

  while (pool.length) {
    const weights = pool.map((t) => weightFor(t, prev, prev2, options));
    const total = weights.reduce((a, b) => a + b, 0);
    let pick = rng() * total;
    let idx = 0;
    for (; idx < pool.length - 1; idx++) {
      pick -= weights[idx];
      if (pick <= 0) break;
    }
    const [chosen] = pool.splice(idx, 1);
    out.push(chosen);
    prev2 = prev;
    prev = chosen;
  }
  return out;
}
