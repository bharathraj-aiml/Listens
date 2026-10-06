import { create } from "zustand";
import type { User } from "@/lib/types";

const KEY = "listens.auth";

interface AuthState {
  /** false until localStorage has been read (avoids a flash of the login page on reload). */
  ready: boolean;
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  load: () => void;
  setTokens: (access: string, refresh: string) => void;
  setUser: (user: User | null) => void;
  clear: () => void;
}

function persist(access: string | null, refresh: string | null) {
  try {
    if (access && refresh) localStorage.setItem(KEY, JSON.stringify({ access, refresh }));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable (private mode): the session just won't survive a reload */
  }
}

// Tokens live in localStorage: simple and fine for a self-hosted portfolio app. The trade-off is
// that any XSS could read them; a production app would use httpOnly cookies + CSRF protection.
export const useAuth = create<AuthState>((set) => ({
  ready: false,
  accessToken: null,
  refreshToken: null,
  user: null,
  load: () => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const { access, refresh } = JSON.parse(raw);
        set({ accessToken: access, refreshToken: refresh });
      }
    } catch {
      /* ignore corrupt storage */
    }
    set({ ready: true });
  },
  setTokens: (access, refresh) => {
    persist(access, refresh);
    set({ accessToken: access, refreshToken: refresh });
  },
  setUser: (user) => set({ user }),
  clear: () => {
    persist(null, null);
    set({ accessToken: null, refreshToken: null, user: null });
  },
}));
