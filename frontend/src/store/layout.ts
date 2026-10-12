import { create } from "zustand";

const KEY = "listens.sidebarCollapsed";

interface LayoutState {
  /** desktop sidebar shrunk to an icon rail */
  sidebarCollapsed: boolean;
  load: () => void;
  toggleSidebar: () => void;
}

/** Remembered per browser. Read after mount (not at module load) so the server-rendered markup always matches
 *  the first client render; a stored "collapsed" then applies a moment later. */
export const useLayout = create<LayoutState>((set, get) => ({
  sidebarCollapsed: false,
  load: () => {
    try {
      if (localStorage.getItem(KEY) === "1") set({ sidebarCollapsed: true });
    } catch {
      /* storage unavailable: the choice just won't survive a reload */
    }
  },
  toggleSidebar: () => {
    const next = !get().sidebarCollapsed;
    set({ sidebarCollapsed: next });
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
  },
}));
