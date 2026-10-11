const KEY = "listens.recentPlays";
const MAX_ENTRIES = 300;

/** When each track last started playing, kept on this device so the shuffle can avoid replaying what
 *  you just heard. Best effort: storage can be unavailable (private mode), then it is simply empty. */
export function getRecentPlays(): Map<string, number> {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return new Map(Object.entries(raw).filter(([, t]) => typeof t === "number") as [string, number][]);
  } catch {
    return new Map();
  }
}

export function recordPlay(trackId: string, now = Date.now()) {
  try {
    const entries = [...getRecentPlays().entries(), [trackId, now] as [string, number]];
    const latest = new Map(entries); // a repeat play overwrites its earlier time
    const kept = [...latest.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_ENTRIES);
    localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(kept)));
  } catch {
    /* storage unavailable: shuffle just has no history */
  }
}
