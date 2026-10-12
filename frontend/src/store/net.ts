import { create } from "zustand";
import { longestWait, SLOW_MS } from "@/lib/net";

interface NetState {
  /** how long the oldest pending request has waited, only once it is past SLOW_MS (else 0) */
  waitedMs: number;
}

export const useNet = create<NetState>(() => ({ waitedMs: 0 }));

const pending = new Map<number, number>();
let seq = 0;
let timer: ReturnType<typeof setInterval> | null = null;

function tick() {
  const waited = longestWait(pending.values(), Date.now());
  const next = waited >= SLOW_MS ? waited : 0;
  if (useNet.getState().waitedMs !== next) useNet.setState({ waitedMs: next });
  if (!pending.size && timer) {
    clearInterval(timer);
    timer = null;
  }
}

/** Mark a request as in flight; call the returned function when it settles. Drives the "waking up the
 *  server" banner, which appears only if a request stays pending past SLOW_MS. */
export function trackRequest(): () => void {
  const id = ++seq;
  pending.set(id, Date.now());
  if (!timer && typeof window !== "undefined") timer = setInterval(tick, 500);
  return () => {
    pending.delete(id);
    tick();
  };
}
