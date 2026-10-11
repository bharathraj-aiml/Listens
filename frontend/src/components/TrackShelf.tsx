"use client";

import Cover from "@/components/Cover";
import { PlayIcon } from "@/components/icons";
import type { Track } from "@/lib/types";
import { currentTrack, usePlayer } from "@/store/player";

/** One horizontal, swipeable row of cover cards. Tapping a card plays the shelf from that track. */
export default function TrackShelf({ id, title, tracks }: { id: string; title: string; tracks: Track[] }) {
  const playQueue = usePlayer((s) => s.playQueue);
  const current = usePlayer(currentTrack);
  const playing = usePlayer((s) => s.playing);
  const playable = tracks.filter((t) => t.status === "ready");
  if (!playable.length) return null;

  return (
    <section aria-labelledby={id}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id={id} className="text-lg font-semibold tracking-tight">{title}</h2>
        <button
          data-testid="play-all"
          aria-label={`Play all in ${title}`}
          onClick={() => playQueue(playable, 0)}
          className="flex size-11 items-center justify-center rounded-full border border-line bg-raise text-fg transition-colors hover:bg-accent hover:text-ink active:scale-95"
        >
          <PlayIcon />
        </button>
      </div>
      <ul className="-mx-4 flex snap-x snap-mandatory scroll-pl-4 gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] md:mx-0 md:scroll-pl-0 md:px-0 [&::-webkit-scrollbar]:hidden">
        {playable.map((t, i) => {
          const isCurrent = current?.id === t.id;
          return (
            <li key={t.id} className="w-[132px] shrink-0 snap-start">
              <button
                aria-label={`Play ${t.title}`}
                onClick={() => playQueue(playable, i)}
                className="group block w-full text-left"
              >
                <span className="relative block">
                  <Cover id={t.id} url={t.cover_url} size={132} className="aspect-square w-full rounded-2xl transition-transform group-active:scale-[0.98]" />
                  {isCurrent && playing && (
                    <span aria-label="Now playing" className="absolute bottom-2 left-2 flex h-3 items-end gap-0.5 rounded bg-black/50 px-1 py-1">
                      {[0, 0.2, 0.4].map((d) => <i key={d} className="eq-bar block h-3 w-0.5 bg-accent" style={{ animationDelay: `${d}s` }} />)}
                    </span>
                  )}
                </span>
                <span className={`mt-2 block truncate text-sm font-medium ${isCurrent ? "text-accent" : ""}`}>{t.title}</span>
                <span className="block truncate text-xs text-muted">{t.artist.name}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function ShelfSkeleton() {
  return (
    <div aria-hidden className="space-y-3">
      <div className="h-6 w-40 animate-pulse rounded-lg bg-raise motion-reduce:animate-none" />
      <div className="flex gap-3 overflow-hidden">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="w-[132px] shrink-0 space-y-2">
            <div className="aspect-square w-full animate-pulse rounded-2xl bg-raise motion-reduce:animate-none" />
            <div className="h-3 w-24 animate-pulse rounded bg-raise motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    </div>
  );
}
