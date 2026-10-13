import type { Track } from "./types.ts";

/** A song only counts as "recently played" once it has been playing this long, matching the server rule
 *  (a song skipped sooner than this is a tap-through, not a listen: catalogue QUICK_SKIP_MS). */
export const LISTEN_AFTER_MS = 8000;
export const RECENTS_MAX = 20;

export interface LocalRecent {
  track: Track;
  /** epoch ms when the song reached LISTEN_AFTER_MS on this device */
  at: number;
}

/** Recently played = what the server remembers (every device) merged with what this device just played.
 *  The server list lags by however long the request takes, and a refetch is only a snapshot, so this
 *  device's own listens are layered on top of it the instant they happen. Each song appears once, at its
 *  newest time; only ready songs are shown. Server songs that carry no time keep the server's own order,
 *  after anything with a real time. */
export function mergeRecents(server: Track[], local: LocalRecent[], limit = RECENTS_MAX): Track[] {
  const best = new Map<string, { track: Track; at: number; fromLocal: boolean }>();
  const offer = (track: Track, at: number, fromLocal: boolean) => {
    const have = best.get(track.id);
    if (!have || at > have.at || (at === have.at && fromLocal)) best.set(track.id, { track, at, fromLocal });
  };
  const fresh = new Map(server.map((t) => [t.id, t]));
  let newestServer = -Infinity;
  server.forEach((track, i) => {
    const parsed = track.played_at ? Date.parse(track.played_at) : NaN;
    if (Number.isFinite(parsed)) newestServer = Math.max(newestServer, parsed);
    offer(track, Number.isFinite(parsed) ? parsed : -1 - i, false);
  });
  // The server is the authority on anything it has had time to hear about. A song stored on this device that the server
  // does not list, although it is OLDER than the server's newest listen, no longer exists (deleted or merged as a
  // duplicate): showing it would be a dead tile with a broken cover that cannot play. Newer than the server's newest
  // listen means the server just has not caught up yet, so those stay. With no server data at all, everything stays.
  const synced = (l: LocalRecent) => fresh.size === 0 || fresh.has(l.track.id) || l.at > newestServer;
  local.filter(synced).forEach((l) => offer(l.track, l.at, true));
  return [...best.values()]
    .filter((x) => x.track.status === "ready")
    .sort((a, b) => b.at - a.at || Number(b.fromLocal) - Number(a.fromLocal))
    .slice(0, limit)
    // This device's time wins, but the server's copy of the song wins: a song stored on the device days ago carries a
    // signed cover link that has since expired, while the server's copy always has a fresh one.
    .map((x) => fresh.get(x.track.id) ?? x.track);
}
