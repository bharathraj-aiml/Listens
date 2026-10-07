import { create } from "zustand";
import { api, get as apiGet } from "@/lib/api";

interface LikesState {
  ids: Set<string>;
  loaded: boolean;
  load: () => Promise<void>;
  isLiked: (trackId: string) => boolean;
  toggle: (trackId: string) => Promise<void>;
}

// A session-wide set of liked track ids, loaded once (one cheap query) so every TrackList row
// and the player bar can show heart state without an N+1 fetch per track.
export const useLikes = create<LikesState>((set, get) => ({
  ids: new Set(),
  loaded: false,
  load: async () => {
    if (get().loaded) return;
    try {
      const ids = await apiGet<string[]>("/api/catalogue/likes/ids");
      set({ ids: new Set(ids), loaded: true });
    } catch {
      set({ loaded: true }); // fail open: just show nothing liked rather than blocking the page
    }
  },
  isLiked: (trackId) => get().ids.has(trackId),
  toggle: async (trackId) => {
    const wasLiked = get().ids.has(trackId);
    const optimistic = new Set(get().ids);
    wasLiked ? optimistic.delete(trackId) : optimistic.add(trackId);
    set({ ids: optimistic });
    try {
      await api(`/api/catalogue/likes/${trackId}`, { method: wasLiked ? "DELETE" : "POST" });
    } catch {
      set((s) => {
        const reverted = new Set(s.ids);
        wasLiked ? reverted.add(trackId) : reverted.delete(trackId);
        return { ids: reverted };
      });
    }
  },
}));
