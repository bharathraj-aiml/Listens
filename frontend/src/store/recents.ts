import { create } from "zustand";
import type { LocalRecent } from "@/lib/recents";
import type { Track } from "@/lib/types";

const KEY = (userId: string) => `listens.recents.${userId}`;
const KEEP = 30;

interface RecentsState {
  userId: string | null;
  items: LocalRecent[];
  load: (userId: string) => void;
  add: (track: Track) => void;
}

function persist(userId: string | null, items: LocalRecent[]) {
  if (!userId) return;
  try {
    localStorage.setItem(KEY(userId), JSON.stringify(items));
  } catch {
    /* storage unavailable (private mode): the list just won't survive a reload; the server keeps the history */
  }
}

/** Songs this device has genuinely listened to, newest first, kept per account. Home merges it with the
 *  server's list so a song shows in "Recently played" the moment it counts, without waiting for any refetch. */
export const useRecents = create<RecentsState>((set, get) => ({
  userId: null,
  items: [],
  load: (userId) => {
    if (get().userId === userId) return;
    let items: LocalRecent[] = [];
    try {
      const raw = JSON.parse(localStorage.getItem(KEY(userId)) ?? "[]");
      if (Array.isArray(raw)) items = raw.filter((x) => x?.track?.id && typeof x.at === "number").slice(0, KEEP);
    } catch {
      /* corrupt storage: start empty */
    }
    set({ userId, items });
  },
  add: (track) => {
    const { userId, items } = get();
    const next = [{ track, at: Date.now() }, ...items.filter((x) => x.track.id !== track.id)].slice(0, KEEP);
    set({ items: next });
    persist(userId, next);
  },
}));
