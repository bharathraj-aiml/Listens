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
  seekRequest: { to: number; n: number } | null;

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
  seekRequest: null,

  playQueue: (tracks, startIndex = 0) =>
    set({ queue: tracks, index: tracks.length ? startIndex : -1, playing: tracks.length > 0, currentTime: 0, error: null }),
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
      return { queue, index };
    }),
  jumpTo: (i) => set((s) => (i >= 0 && i < s.queue.length ? { index: i, playing: true, currentTime: 0, error: null } : s)),
  next: () =>
    set((s) =>
      s.index + 1 < s.queue.length
        ? { index: s.index + 1, playing: true, currentTime: 0, error: null }
        : { playing: false }, // end of queue: stop
    ),
  prev: () => {
    const s = get();
    // like most players: past the first 3 s "previous" restarts the track instead of going back
    if (s.currentTime > 3 || s.index <= 0) get().requestSeek(0);
    else set({ index: s.index - 1, playing: true, currentTime: 0, error: null });
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
  setQueueOpen: (queueOpen) => set({ queueOpen }),
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
