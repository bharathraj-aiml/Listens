import { create } from "zustand";

interface NavState {
  stack: string[];
  visit: (path: string) => void;
}

/** In-app page trail behind the back arrow. Landing on a page that is already in the trail cuts
 *  the trail back to it (Home > Profile > Home becomes just Home), and Home always resets it, so
 *  the arrow can never walk in a circle. */
export const useNav = create<NavState>((set, get) => ({
  stack: [],
  visit: (path) => {
    const { stack } = get();
    if (stack[stack.length - 1] === path) return;
    if (path === "/") return set({ stack: ["/"] });
    const at = stack.indexOf(path);
    set({ stack: at === -1 ? [...stack, path] : stack.slice(0, at + 1) });
  },
}));
