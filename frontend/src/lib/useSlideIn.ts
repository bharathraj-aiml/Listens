"use client";

import { useEffect, useRef, useState } from "react";

/** Keeps a panel mounted long enough to play its exit transition before unmounting, so a CSS
 *  `transition-transform` can animate both open AND close instead of the panel just vanishing.
 *  `mounted` gates whether to render at all (eventually false after close, so e2e's
 *  `toHaveCount(0)` still holds); `shown` gates the "in position" class for the transition. */
export function useSlideIn(open: boolean, durationMs = 200) {
  const [mounted, setMounted] = useState(open);
  const [shown, setShown] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (open) {
      if (timer.current) clearTimeout(timer.current);
      setMounted(true);
      const raf = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(raf);
    }
    setShown(false);
    timer.current = setTimeout(() => setMounted(false), durationMs);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [open, durationMs]);

  return { mounted, shown };
}
