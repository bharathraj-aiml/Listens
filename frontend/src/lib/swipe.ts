"use client";

import { useRef } from "react";

interface SwipeHandlers {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  onSwipeDown?: () => void;
  onSwipeUp?: () => void;
  /** Fires on a release that moved less than TAP_THRESHOLD - i.e. a tap, not a swipe. */
  onTap?: () => void;
}

const SWIPE_THRESHOLD = 50; // px of travel before a drag counts as a deliberate swipe
const TAP_THRESHOLD = 10; // px of travel under which a release counts as a tap, not an aborted swipe

/** Single-pointer swipe/tap detection. No gesture library: this is one threshold check on
 *  pointerup, which is all four-direction swipe-or-tap needs - a dependency would buy nothing. */
export function useSwipe(handlers: SwipeHandlers) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  return {
    onPointerDown(e: React.PointerEvent) {
      start.current = { x: e.clientX, y: e.clientY };
    },
    onPointerUp(e: React.PointerEvent) {
      if (!start.current) return;
      const dx = e.clientX - start.current.x;
      const dy = e.clientY - start.current.y;
      start.current = null;
      const h = handlersRef.current;
      if (Math.abs(dx) < TAP_THRESHOLD && Math.abs(dy) < TAP_THRESHOLD) {
        h.onTap?.();
        return;
      }
      if (Math.abs(dx) > Math.abs(dy)) {
        if (dx <= -SWIPE_THRESHOLD) h.onSwipeLeft?.();
        else if (dx >= SWIPE_THRESHOLD) h.onSwipeRight?.();
      } else {
        if (dy <= -SWIPE_THRESHOLD) h.onSwipeUp?.();
        else if (dy >= SWIPE_THRESHOLD) h.onSwipeDown?.();
      }
    },
  };
}
