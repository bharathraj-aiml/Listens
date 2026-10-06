"use client";

import Link from "next/link";
import Cover from "@/components/Cover";
import { PlayIcon, PlusIcon } from "@/components/icons";
import { formatDuration } from "@/lib/format";
import type { Track } from "@/lib/types";
import { currentTrack, usePlayer } from "@/store/player";

const STATUS_STYLE: Record<Track["status"], string> = {
  uploaded: "bg-raise text-muted",
  processing: "bg-glow/15 text-glow",
  ready: "bg-ok/15 text-ok",
  failed: "bg-danger/15 text-danger",
};
const STATUS_LABEL: Record<Track["status"], string> = {
  uploaded: "Queued", processing: "Processing…", ready: "Ready", failed: "Failed",
};

interface Props {
  tracks: Track[];
  showStatus?: boolean;
  onDelete?: (t: Track) => void;
}

export default function TrackList({ tracks, showStatus = false, onDelete }: Props) {
  const playQueue = usePlayer((s) => s.playQueue);
  const addToQueue = usePlayer((s) => s.addToQueue);
  const playNext = usePlayer((s) => s.playNext);
  const current = usePlayer(currentTrack);
  const playing = usePlayer((s) => s.playing);

  // The queue is the *playable* subset of this list, so "next" never lands on an unprocessed track.
  const playable = tracks.filter((t) => t.status === "ready");

  return (
    <ul className="divide-y divide-line/60" data-testid="track-list">
      {tracks.map((t) => {
        const isCurrent = current?.id === t.id;
        const ready = t.status === "ready";
        return (
          <li key={t.id} data-testid="track-row" data-title={t.title} className={`group flex items-center gap-3 px-2 py-2 ${isCurrent ? "bg-raise/70" : "hover:bg-raise/40"}`}>
            <button
              aria-label={`Play ${t.title}`}
              data-testid="row-play"
              disabled={!ready}
              onClick={() => playQueue(playable, playable.findIndex((p) => p.id === t.id))}
              className="relative shrink-0 disabled:cursor-not-allowed"
            >
              <Cover id={t.id} url={t.cover_url} size={44} />
              {ready && (
                <span className="absolute inset-0 grid place-items-center rounded-md bg-black/50 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100">
                  <PlayIcon />
                </span>
              )}
            </button>
            <div className="min-w-0 flex-1">
              <div className={`flex items-center gap-2 truncate text-sm ${isCurrent ? "text-accent" : ""}`}>
                {isCurrent && playing && (
                  <span aria-label="Now playing" className="flex h-3 items-end gap-0.5">
                    {[0, 0.2, 0.4].map((d) => <i key={d} className="eq-bar block h-3 w-0.5 bg-accent" style={{ animationDelay: `${d}s` }} />)}
                  </span>
                )}
                <span className="truncate">{t.title}</span>
              </div>
              <div className="truncate text-xs text-muted">
                <Link href={`/artist/${t.artist.id}`} className="hover:text-fg hover:underline">{t.artist.name}</Link>
                {t.album && (
                  <>
                    {" · "}
                    <Link href={`/album/${t.album.id}`} className="hover:text-fg hover:underline">{t.album.title}</Link>
                  </>
                )}
              </div>
              {t.status === "failed" && t.error && <div className="truncate text-xs text-danger" title={t.error}>{t.error}</div>}
            </div>
            {showStatus && (
              <span data-testid="track-status" className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[t.status]}`}>{STATUS_LABEL[t.status]}</span>
            )}
            {ready && (
              <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 group-focus-within:opacity-100">
                <button aria-label={`Play ${t.title} next`} title="Play next" onClick={() => playNext(t)} className="rounded px-1.5 py-1 text-xs text-muted hover:text-fg">Next</button>
                <button aria-label={`Add ${t.title} to queue`} title="Add to queue" onClick={() => addToQueue(t)} className="rounded p-1 text-muted hover:text-fg"><PlusIcon width={18} height={18} /></button>
              </div>
            )}
            <span className="hidden w-12 text-right text-xs tabular-nums text-muted sm:block">{formatDuration(t.duration_ms)}</span>
            {onDelete && (
              <button aria-label={`Delete ${t.title}`} onClick={() => onDelete(t)} className="rounded px-1.5 py-1 text-xs text-muted hover:text-danger">Delete</button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function PlayAllButton({ tracks }: { tracks: Track[] }) {
  const playQueue = usePlayer((s) => s.playQueue);
  const ready = tracks.filter((t) => t.status === "ready");
  if (!ready.length) return null;
  return (
    <button data-testid="play-all" onClick={() => playQueue(ready, 0)} className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-ink hover:brightness-110">
      <PlayIcon /> Play all
    </button>
  );
}
