import type { ArtistRef, Track } from "./types.ts";

/** Everyone credited on a track, in credit order (the first is the primary artist). Older API responses only
 *  carry `artist`, so fall back to it. */
export function creditOf(t: Pick<Track, "artist" | "artists">): ArtistRef[] {
  return t.artists && t.artists.length ? t.artists : [t.artist];
}

/** The credit as text: "Yuvan Shankar Raja, Na.Muthukumar". */
export function creditText(t: Pick<Track, "artist" | "artists">): string {
  return creditOf(t).map((a) => a.name).join(", ");
}

/** True when the two tracks share any credited artist (used by the shuffle to avoid same-artist runs). */
export function sharesArtist(a: Pick<Track, "artist" | "artists">, b: Pick<Track, "artist" | "artists">): boolean {
  const ids = new Set(creditOf(a).map((x) => x.id));
  return creditOf(b).some((x) => ids.has(x.id));
}
