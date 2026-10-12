/** Requests slower than this are worth telling the listener about: normal API calls answer well inside it, so
 *  anything longer means the server was asleep and is starting up (free hosting sleeps when idle). */
export const SLOW_MS = 3000;

/** How long the oldest still-pending request has been waiting, or 0 when nothing is pending. */
export function longestWait(starts: Iterable<number>, now: number): number {
  let oldest = Infinity;
  for (const start of starts) oldest = Math.min(oldest, start);
  return oldest === Infinity ? 0 : Math.max(0, now - oldest);
}
