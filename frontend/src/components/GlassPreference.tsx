"use client";

import { useEffect } from "react";
import { usePlayer } from "@/store/player";

/** Renders nothing. Mirrors the "follow system transparency" preference onto <html> so the glass CSS
 *  (globals.css) can opt in to the OS "reduce transparency" setting. Off by default. */
export default function GlassPreference() {
  const follow = usePlayer((s) => s.followSystemTransparency);
  useEffect(() => {
    document.documentElement.toggleAttribute("data-follow-system-transparency", follow);
  }, [follow]);
  return null;
}
