"use client";

import { useEffect, useState } from "react";
import { CloseIcon } from "@/components/icons";
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

  if (!open) return null;

  return (
    <aside
      data-testid="similar-panel"
      aria-label="Similar tracks"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-line bg-panel shadow-2xl"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-semibold">Similar tracks</h2>
          {track && <p className="truncate text-xs text-muted">Based on {track.title}</p>}
        </div>
        <button aria-label="Close similar tracks" onClick={() => setOpen(false)} className="flex size-11 shrink-0 items-center justify-center rounded-full text-muted hover:text-fg">
          <CloseIcon />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto pb-40">
        {!track && <p className="px-4 py-8 text-sm text-muted">Nothing playing.</p>}
        {track && error && <p role="alert" className="px-4 py-8 text-sm text-danger">{error}</p>}
        {track && !error && !tracks && <p className="px-4 py-8 text-sm text-muted">Loading…</p>}
        {track && tracks && tracks.length === 0 && (
          <p data-testid="similar-empty" className="px-4 py-8 text-center text-sm text-muted">No similar tracks found yet.</p>
        )}
        {track && tracks && tracks.length > 0 && <TrackList tracks={tracks} />}
      </div>
    </aside>
  );
}
