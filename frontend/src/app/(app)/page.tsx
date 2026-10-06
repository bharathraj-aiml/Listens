"use client";

import { useEffect, useState } from "react";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import { get } from "@/lib/api";
import type { Track } from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function Home() {
  const user = useAuth((s) => s.user);
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Track[]>("/api/catalogue/tracks?limit=100").then(setTracks).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Good listening{user ? `, ${user.display_name}` : ""}
        </h1>
        <p className="text-sm text-muted">Everything in your library</p>
      </header>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {tracks === null && !error && <p className="text-muted">Loading…</p>}
      {tracks && tracks.length === 0 && (
        <div className="rounded-xl border border-dashed border-line p-8 text-center text-muted">
          No music yet. <a href="/upload" className="text-accent underline">Upload some</a> to get started.
        </div>
      )}
      {tracks && tracks.length > 0 && (
        <section aria-labelledby="new">
          <div className="mb-2 flex items-center justify-between">
            <h2 id="new" className="text-lg font-medium">New uploads</h2>
            <PlayAllButton tracks={tracks} />
          </div>
          <TrackList tracks={tracks} />
        </section>
      )}
    </div>
  );
}
