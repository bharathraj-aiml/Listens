"use client";

import { useEffect } from "react";
import { LISTEN_AFTER_MS } from "@/lib/recents";
import { useAuth } from "@/store/auth";
import { currentTrack, usePlayer } from "@/store/player";
import { useRecents } from "@/store/recents";

/** Renders nothing. Records a song into the live "Recently played" list once it has been playing for
 *  LISTEN_AFTER_MS, so tapping through songs doesn't fill it, and a song you stay with appears at once. */
export default function RecentsTracker() {
  const userId = useAuth((s) => s.user?.id);
  const load = useRecents((s) => s.load);
  const trackId = usePlayer((s) => currentTrack(s)?.id);

  useEffect(() => {
    if (userId) load(userId);
  }, [userId, load]);

  useEffect(() => {
    if (!trackId) return;
    const timer = setTimeout(() => {
      const state = usePlayer.getState();
      const track = currentTrack(state);
      if (track?.id === trackId && state.playing) useRecents.getState().add(track);
    }, LISTEN_AFTER_MS);
    return () => clearTimeout(timer); // the song changed (or stopped) before it counted
  }, [trackId]);

  return null;
}
