/** Pages fetch in useEffect, so going Back remounts them and they refetch, which looks like a page
 *  refresh (spinner, scroll jump). For a moment after a back navigation, GETs are answered from
 *  the last response instead. Cleared on every non-GET and whenever the auth tokens change, so
 *  edits are never hidden and one account's data never reaches another. */
const REUSE_MS = 5 * 60_000;
const WINDOW_MS = 2000;

const entries = new Map<string, { at: number; data: unknown }>();
let backNavUntil = 0;

export function markBackNavigation() {
  backNavUntil = Date.now() + WINDOW_MS;
}

export function clearResponseCache() {
  entries.clear();
}

export function cachedForBackNavigation<T>(path: string): T | undefined {
  if (Date.now() >= backNavUntil) return undefined;
  const hit = entries.get(path);
  return hit && Date.now() - hit.at < REUSE_MS ? (hit.data as T) : undefined;
}

export function rememberResponse(path: string, data: unknown) {
  entries.set(path, { at: Date.now(), data });
}
