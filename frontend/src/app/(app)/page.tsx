"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Cover from "@/components/Cover";
import { PauseIcon, PlayIcon } from "@/components/icons";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import TrackShelf, { ShelfSkeleton } from "@/components/TrackShelf";
import { get } from "@/lib/api";
import { mergeRecents } from "@/lib/recents";
import type { Track } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { currentTrack, usePlayer } from "@/store/player";
import { useRecents } from "@/store/recents";

const PREVIEW_COUNT = 10;

/** Jump back in: the last track you played, one tap to resume it with your recents as the queue. */
function Resume({ tracks }: { tracks: Track[] }) {
  const playQueue = usePlayer((s) => s.playQueue);
  const toggle = usePlayer((s) => s.toggle);
  const playing = usePlayer((s) => s.playing);
  const current = usePlayer(currentTrack);
  const last = tracks.find((t) => t.status === "ready");
  if (!last) return null;
  const active = current?.id === last.id;

  return (
    <div className="glass-card flex items-center gap-3 rounded-2xl border border-line bg-panel p-3" data-testid="resume-card">
      <Cover id={last.id} url={last.cover_url} size={56} className="rounded-xl" />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{last.title}</div>
        <div className="truncate text-sm text-muted">{last.artist.name}</div>
      </div>
      <button
        aria-label={active && playing ? "Pause" : `Resume ${last.title}`}
        onClick={() => (active ? toggle() : playQueue(tracks.filter((t) => t.status === "ready"), 0))}
        className="flex size-12 shrink-0 items-center justify-center rounded-full bg-accent text-ink transition-transform hover:brightness-110 active:scale-95"
      >
        {active && playing ? <PauseIcon /> : <PlayIcon />}
      </button>
    </div>
  );
}

export default function Home() {
  const user = useAuth((s) => s.user);
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [serverRecent, setServerRecent] = useState<Track[]>([]);
  const localRecent = useRecents((s) => s.items);
  // What the server remembers plus what this device just played: updates the instant a song counts, no refetch.
  const recentlyPlayed = useMemo(() => mergeRecents(serverRecent, localRecent), [serverRecent, localRecent]);
  const [madeForYou, setMadeForYou] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const refreshRecent = useCallback(() => {
    get<Track[]>("/api/catalogue/home/recently-played").then(setServerRecent).catch(() => {});
  }, []);

  useEffect(() => {
    get<Track[]>("/api/catalogue/tracks?limit=100").then(setTracks).catch((e) => setError(e.message));
    get<Track[]>("/api/catalogue/home/made-for-you").then(setMadeForYou).catch(() => {});
    refreshRecent();
    // Plays on your other devices show up too: re-sync when you come back to the tab, and every minute while it is open.
    const onVisible = () => document.visibilityState === "visible" && refreshRecent();
    document.addEventListener("visibilitychange", onVisible);
    const timer = setInterval(onVisible, 60_000);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(timer);
    };
  }, [refreshRecent]);

  const visible = tracks && !showAll ? tracks.slice(0, PREVIEW_COUNT) : tracks;
  const hidden = tracks ? tracks.length - PREVIEW_COUNT : 0;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Good listening{user ? `, ${user.display_name}` : ""}
        </h1>
        <p className="text-sm text-muted">Pick up where you left off, or find something new.</p>
      </header>

      {error && <p role="alert" className="text-danger">{error}</p>}

      <Resume tracks={recentlyPlayed} />

      {tracks === null && !error && (
        <div className="space-y-8" role="status" aria-label="Loading your library">
          <ShelfSkeleton />
          <ShelfSkeleton />
        </div>
      )}

      <TrackShelf id="recently-played" title="Recently played" tracks={recentlyPlayed} />
      <TrackShelf id="made-for-you" title="Made for you" tracks={madeForYou} />

      {tracks && tracks.length === 0 && (
        <div className="glass-card rounded-2xl border border-dashed border-line p-8 text-center text-muted">
          No music yet.{" "}
          <Link href="/upload" className="text-accent underline">Upload some</Link> to get started.
        </div>
      )}

      {visible && visible.length > 0 && (
        <section aria-labelledby="new">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 id="new" className="text-lg font-semibold tracking-tight">New uploads</h2>
            <PlayAllButton tracks={tracks ?? []} />
          </div>
          <div className="glass-card rounded-2xl border border-line bg-panel p-1">
            <TrackList tracks={visible} />
          </div>
          {hidden > 0 && (
            <button
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
              className="mt-3 w-full rounded-full border border-line py-2.5 text-sm text-muted transition-colors hover:bg-raise hover:text-fg"
            >
              {showAll ? "Show fewer" : `Show all ${tracks!.length} tracks`}
            </button>
          )}
        </section>
      )}
    </div>
  );
}
