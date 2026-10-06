import { post } from "@/lib/api";

interface StreamUrl { url: string; expires_in: number }
const cache = new Map<string, { url: string; expiresAt: number }>();

/** Signed HLS URL for a track (cached until ~1 min before it expires). */
export async function getStreamUrl(trackId: string): Promise<string> {
  const hit = cache.get(trackId);
  if (hit && hit.expiresAt - Date.now() > 60_000) return hit.url;
  const { url, expires_in } = await post<StreamUrl>(`/api/stream/tracks/${trackId}/url`);
  cache.set(trackId, { url, expiresAt: Date.now() + expires_in * 1000 });
  return url;
}

/** Forget a cached URL (e.g. the server rejected it as expired) so the next call mints a new one. */
export function invalidateStreamUrl(trackId: string) {
  cache.delete(trackId);
}

const playlistLines = (text: string) => text.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));

/**
 * Warm the browser HTTP cache for the next track: signed URL, master playlist, the variant
 * playlist and its first segment. Responses carry `Cache-Control: private, max-age=3600`, so when
 * hls.js later requests the same URLs they're served locally and the next track starts instantly.
 * `kbps` picks the variant to warm ("auto" starts at the top quality, see PlayerEngine).
 */
export async function prefetchTrack(trackId: string, kbps: "auto" | number): Promise<void> {
  const masterUrl = new URL(await getStreamUrl(trackId), window.location.href);
  const variants = playlistLines(await (await fetch(masterUrl)).text());
  if (!variants.length) return;
  const wanted = kbps === "auto" ? undefined : variants.find((v) => v.startsWith(`q${kbps}/`));
  const variantUrl = new URL(wanted ?? variants[variants.length - 1], masterUrl);
  const segments = playlistLines(await (await fetch(variantUrl)).text());
  if (segments[0]) await (await fetch(new URL(segments[0], variantUrl))).arrayBuffer();
}
