"use client";

import { useEffect, useState } from "react";
import SidePanel from "@/components/SidePanel";
import TrackList from "@/components/TrackList";
import { get } from "@/lib/api";
import type { Track } from "@/lib/types";
import { currentTrack, usePlayer } from "@/store/player";

export default function SimilarTracksPanel() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.similarOpen);
  const setOpen = usePlayer((s) => s.setSimilarOpen);
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !track) return;
    let stale = false;
    setTracks(null);
    setError(null);
    get<Track[]>(`/api/catalogue/tracks/${track.id}/similar`)
      .then((d) => !stale && setTracks(d))
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [open, track?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <SidePanel
      open={open}
      onClose={() => setOpen(false)}
      title="Similar tracks"
      subtitle={track ? `Based on ${track.title}` : undefined}
      testId="similar-panel"
      ariaLabel="Similar tracks"
    >
      {!track && <p className="px-4 py-8 text-sm text-muted">Nothing playing.</p>}
      {track && error && <p role="alert" className="px-4 py-8 text-sm text-danger">{error}</p>}
      {track && !error && !tracks && <p className="px-4 py-8 text-sm text-muted">Loading…</p>}
      {track && tracks && tracks.length === 0 && (
        <p data-testid="similar-empty" className="px-4 py-8 text-center text-sm text-muted">No similar tracks found yet.</p>
      )}
      {track && tracks && tracks.length > 0 && <TrackList tracks={tracks} />}
    </SidePanel>
  );
}
