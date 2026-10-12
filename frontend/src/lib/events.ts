import { api } from "@/lib/api";

export type ClientEventType = "play_start" | "play_end" | "skip";

interface EventBody {
  event_type: ClientEventType;
  track_id: string;
  ms_played?: number;
  position_ms?: number;
  reason?: string;
}

/** Fire-and-forget: a lost analytics event is never worth surfacing an error to the listener.
 *  Not flushed on tab-close (navigator.sendBeacon can't carry an Authorization header, and
 *  putting an access token in a URL query string just to use it is worse than losing the
 *  occasional trailing event) - covers play_start on load and play_end/skip on track change,
 *  which is the overwhelming majority of real listening sessions. */
export function recordEvent(body: EventBody): void {
  api("/api/catalogue/events", { method: "POST", body: JSON.stringify(body) }, true, { quiet: true }).catch(() => {});
}
