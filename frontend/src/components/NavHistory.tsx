"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { markBackNavigation } from "@/lib/responseCache";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { useNav } from "@/store/nav";
import { usePlayer } from "@/store/player";

/** Closes the topmost open overlay: lyrics/queue/similar sit above the Now Playing sheet. */
function closeTopOverlay() {
  const s = usePlayer.getState();
  if (s.lyricsOpen) s.setLyricsOpen(false);
  else if (s.queueOpen) s.setQueueOpen(false);
  else if (s.similarOpen) s.setSimilarOpen(false);
  else if (s.nowPlayingOpen) s.setNowPlayingOpen(false);
}

/** Renders nothing. Two jobs:
 *  1. Feeds the page trail used by the back arrow.
 *  2. On phones, gives each open overlay (lyrics, queue, similar, Now Playing) its own history
 *     entry, so the back button/gesture closes the overlay instead of leaving the page. Closing an
 *     overlay with its own button removes that entry again, so history stays in step. */
export default function NavHistory() {
  const pathname = usePathname();
  const visit = useNav((s) => s.visit);
  const isPhone = useMediaQuery("(max-width: 767px)");
  const openOverlays = usePlayer((s) => Number(s.lyricsOpen) + Number(s.queueOpen) + Number(s.similarOpen) + Number(s.nowPlayingOpen));
  // Phone only: on desktop the panels are side panels and shouldn't take over the Back button.
  const count = isPhone ? openOverlays : 0;
  const pushed = useRef(0);
  const skipPops = useRef(0);

  useEffect(() => { visit(pathname); }, [pathname, visit]);

  useEffect(() => {
    const onPop = () => {
      markBackNavigation();
      if (skipPops.current > 0) {
        skipPops.current--;
        return;
      }
      if (pushed.current > 0) {
        pushed.current--;
        closeTopOverlay();
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (count > pushed.current) {
      for (let i = pushed.current; i < count; i++) window.history.pushState(window.history.state, "", window.location.href);
      pushed.current = count;
    } else if (count < pushed.current) {
      const extra = pushed.current - count;
      pushed.current = count;
      skipPops.current++;
      window.history.go(-extra);
    }
  }, [count]);

  return null;
}
