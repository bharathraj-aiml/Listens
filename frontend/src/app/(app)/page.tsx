"use client";

import { useEffect, useState } from "react";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import { get } from "@/lib/api";
import type { Track } from "@/lib/types";
import { useAuth } from "@/store/auth";

function Section({ id, title, tracks }: { id: string; title: string; tracks: Track[] }) {
  if (!tracks.length) return null;
  return (
    <section aria-labelledby={id}>
      <div className="mb-2 flex items-center justify-between">
        <h2 id={id} className="text-lg font-medium">{title}</h2>
        <PlayAllButton tracks={tracks} />
      </div>
      <TrackList tracks={tracks} />
    </section>
  );
}

export default function Home() {
  const user = useAuth((s) => s.user);
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [recentlyPlayed, setRecentlyPlayed] = useState<Track[]>([]);
  const [madeForYou, setMadeForYou] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Track[]>("/api/catalogue/tracks?limit=100").then(setTracks).catch((e) => setError(e.message));
    get<Track[]>("/api/catalogue/home/recently-played").then(setRecentlyPlayed).catch(() => {});
    get<Track[]>("/api/catalogue/home/made-for-you").then(setMadeForYou).catch(() => {});
  }, []);

  return (
    <div className="space-y-8">
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
      <Section id="recently-played" title="Recently played" tracks={recentlyPlayed} />
      <Section id="made-for-you" title="Made for you" tracks={madeForYou} />
      {tracks && tracks.length > 0 && <Section id="new" title="New uploads" tracks={tracks} />}
    </div>
  );
}
