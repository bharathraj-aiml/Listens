import { create } from "zustand";
import type { Track } from "@/lib/types";

export type Quality = "auto" | number; // number = kbps (96 / 160 / 320)

const PREFS_KEY = "listens.player";

function loadPrefs(): { volume: number; quality: Quality } {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}");
    return {
      volume: typeof p.volume === "number" ? Math.min(1, Math.max(0, p.volume)) : 0.8,
      quality: p.quality === "auto" || typeof p.quality === "number" ? p.quality : "auto",
    };
  } catch {
    return { volume: 0.8, quality: "auto" };
  }
}

function savePrefs(volume: number, quality: Quality) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({ volume, quality }));
  } catch {
    /* ignore */
  }
}

interface PlayerState {
  queue: Track[];
  index: number; // -1 when the queue is empty
  playing: boolean; // user intent; PlayerEngine makes the <audio> element follow it
  currentTime: number;
  duration: number;
  buffering: boolean;
  error: string | null;
  volume: number;
  muted: boolean;
  quality: Quality;
  levels: number[]; // kbps renditions the current track offers (empty until its manifest loads)
  queueOpen: boolean;
  lyricsOpen: boolean;
  similarOpen: boolean;
  seekRequest: { to: number; n: number } | null;
  /** Set by whichever store action caused the most recent track change, read (and cleared)
   *  by PlayerEngine to tag the outgoing track's analytics event as a "skip" with a reason,
   *  vs. a natural play_end. Null means "no deliberate change happened" (e.g. first track). */
  lastSkipReason: string | null;

  playQueue: (tracks: Track[], startIndex?: number) => void;
  addToQueue: (track: Track) => void;
  playNext: (track: Track) => void;
  removeAt: (i: number) => void;
  jumpTo: (i: number) => void;
  next: () => void;
  prev: () => void;
  toggle: () => void;
  setPlaying: (p: boolean) => void;
  requestSeek: (seconds: number) => void;
  setVolume: (v: number) => void;
  toggleMute: () => void;
  setQuality: (q: Quality) => void;
  setQueueOpen: (open: boolean) => void;
  setLyricsOpen: (open: boolean) => void;
  setSimilarOpen: (open: boolean) => void;
  // engine -> store
  setTime: (t: number) => void;
  setDuration: (d: number) => void;
  setBuffering: (b: boolean) => void;
  setError: (e: string | null) => void;
  setLevels: (l: number[]) => void;
}

export const usePlayer = create<PlayerState>((set, get) => ({
  queue: [],
  index: -1,
  playing: false,
  currentTime: 0,
  duration: 0,
  buffering: false,
  error: null,
  volume: 0.8,
  muted: false,
  quality: "auto",
  levels: [],
  queueOpen: false,
  lyricsOpen: false,
  similarOpen: false,
  seekRequest: null,
  lastSkipReason: null,

  playQueue: (tracks, startIndex = 0) =>
    set((s) => {
      const current = s.index >= 0 ? s.queue[s.index] : null;
      const next = tracks.length ? tracks[startIndex] : null;
      const reason = current && next && current.id !== next.id ? "track_select" : s.lastSkipReason;
      return { queue: tracks, index: tracks.length ? startIndex : -1, playing: tracks.length > 0, currentTime: 0, error: null, lastSkipReason: reason };
    }),
  addToQueue: (track) =>
    set((s) => (s.queue.length ? { queue: [...s.queue, track] } : { queue: [track], index: 0, playing: true, currentTime: 0 })),
  playNext: (track) =>
    set((s) => {
      if (!s.queue.length) return { queue: [track], index: 0, playing: true, currentTime: 0 };
      const q = [...s.queue];
      q.splice(s.index + 1, 0, track);
      return { queue: q };
    }),
  removeAt: (i) =>
    set((s) => {
      const queue = s.queue.filter((_, k) => k !== i);
      if (!queue.length) return { queue, index: -1, playing: false };
      // removing before the current track shifts it left; removing the current one lets the next slide in
      const index = i < s.index ? s.index - 1 : Math.min(s.index, queue.length - 1);
      return { queue, index, lastSkipReason: i === s.index ? "track_select" : s.lastSkipReason };
    }),
  jumpTo: (i) =>
    set((s) => (i >= 0 && i < s.queue.length ? { index: i, playing: true, currentTime: 0, error: null, lastSkipReason: "track_select" } : s)),
  next: () =>
    set((s) =>
      s.index + 1 < s.queue.length
        ? { index: s.index + 1, playing: true, currentTime: 0, error: null, lastSkipReason: "next_button" }
        : { playing: false }, // end of queue: stop
    ),
  prev: () => {
    const s = get();
    // like most players: past the first 3 s "previous" restarts the track instead of going back
    if (s.currentTime > 3 || s.index <= 0) get().requestSeek(0);
    else set({ index: s.index - 1, playing: true, currentTime: 0, error: null, lastSkipReason: "previous_button" });
  },
  toggle: () => set((s) => (s.index >= 0 ? { playing: !s.playing } : s)),
  setPlaying: (playing) => set({ playing }),
  requestSeek: (to) => set((s) => ({ seekRequest: { to, n: (s.seekRequest?.n ?? 0) + 1 }, currentTime: to })),
  setVolume: (volume) => {
    set({ volume, muted: false });
    savePrefs(volume, get().quality);
  },
  toggleMute: () => set((s) => ({ muted: !s.muted })),
  setQuality: (quality) => {
    set({ quality });
    savePrefs(get().volume, quality);
  },
  // Mutually exclusive: all three are fixed inset-y-0 side panels, so more than one open at once would overlap.
  setQueueOpen: (queueOpen) => set({ queueOpen, lyricsOpen: queueOpen ? false : get().lyricsOpen, similarOpen: queueOpen ? false : get().similarOpen }),
  setLyricsOpen: (lyricsOpen) => set({ lyricsOpen, queueOpen: lyricsOpen ? false : get().queueOpen, similarOpen: lyricsOpen ? false : get().similarOpen }),
  setSimilarOpen: (similarOpen) => set({ similarOpen, queueOpen: similarOpen ? false : get().queueOpen, lyricsOpen: similarOpen ? false : get().lyricsOpen }),
  setTime: (currentTime) => set({ currentTime }),
  setDuration: (duration) => set({ duration }),
  setBuffering: (buffering) => set({ buffering }),
  setError: (error) => set({ error }),
  setLevels: (levels) => set({ levels }),
}));

export const currentTrack = (s: PlayerState): Track | null => (s.index >= 0 ? s.queue[s.index] ?? null : null);

/** Call once on the client to restore saved volume/quality. */
export function hydratePlayerPrefs() {
  const { volume, quality } = loadPrefs();
  usePlayer.setState({ volume, quality });
}
