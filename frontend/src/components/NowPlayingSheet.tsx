"use client";

import Cover, { hue } from "@/components/Cover";
import {
  CaretDownIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, QueueIcon, RepeatIcon, RepeatOnceIcon,
  ShuffleIcon, SimilarIcon,
} from "@/components/icons";
import LikeButton from "@/components/LikeButton";
import LyricsView from "@/components/LyricsView";
import { hslToRgbTriplet, useDominantColor } from "@/lib/color";
import { formatTime } from "@/lib/format";
import { useSlideIn } from "@/lib/useSlideIn";
import { useSwipe } from "@/lib/swipe";
import { currentTrack, usePlayer } from "@/store/player";

/** Mobile-only full-screen "Now Playing" view, modeled on Spotify/Apple Music: the slim
 *  mini-player (PlayerBar) only has room for cover + title + play/pause + prev/next, so every
 *  other control - shuffle, repeat, seek, queue, similar tracks, and lyrics - lives here, one
 *  tap or swipe away. The whole thing scrolls: lyrics are an inline section at the bottom, not
 *  a separate screen, matching how both of those apps actually lay this out. */
export default function NowPlayingSheet() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.nowPlayingOpen);
  const setOpen = usePlayer((s) => s.setNowPlayingOpen);
  const p = usePlayer();
  const { mounted, shown } = useSlideIn(open);
  const sheetSwipe = useSwipe({ onSwipeDown: () => setOpen(false) });
  const coverSwipe = useSwipe({ onSwipeLeft: p.next, onSwipeRight: p.prev });

  // Ambient wash behind the whole sheet, like Spotify/Apple Music's Now Playing screen: a real
  // color sampled from the cover when there is one, else the same deterministic per-track hue
  // Cover.tsx uses for its placeholder gradient - so even an uncovered track gets some color.
  const fallbackColor = track ? hslToRgbTriplet(hue(track.id), 45, 28) : "0, 0, 0";
  const ambient = useDominantColor(track?.cover_url ?? null, fallbackColor);

  if (!mounted || !track) return null;
  const duration = p.duration || (track.duration_ms ?? 0) / 1000;
  const hasNext = p.index + 1 < p.queue.length;

  return (
    <div
      data-testid="now-playing-sheet"
      aria-label="Now playing"
      style={{ background: `radial-gradient(ellipse 100% 60% at 50% 0%, rgba(${ambient}, 0.4), transparent), var(--color-ink)` }}
      className={`fixed inset-0 z-[35] flex flex-col overflow-y-auto transition-[transform,background] duration-200 ease-out motion-reduce:transition-none md:hidden ${shown ? "translate-y-0" : "translate-y-full"}`}
    >
      {/* swipe-down-to-close only on the top area, not the whole scrollable sheet - otherwise a
          vertical scroll gesture over the lyrics section below could be mistaken for a dismiss */}
      <div onPointerDown={sheetSwipe.onPointerDown} onPointerUp={sheetSwipe.onPointerUp} className="shrink-0">
        <header className="grid grid-cols-[44px_1fr_44px] items-center px-2 py-3">
          <button aria-label="Close now playing" onClick={() => setOpen(false)} className="flex size-11 items-center justify-center rounded-full text-muted hover:text-fg">
            <CaretDownIcon />
          </button>
          <span className="truncate text-center text-xs font-medium uppercase tracking-wide text-muted">Now playing</span>
        </header>

        <div className="flex flex-col items-center gap-6 px-8 pb-8 pt-2">
          <div
            key={track.id}
            onPointerDown={coverSwipe.onPointerDown}
            onPointerUp={coverSwipe.onPointerUp}
            style={{ boxShadow: `0 24px 48px -12px rgba(${ambient}, 0.5)` }}
            className="w-full max-w-xs touch-pan-y animate-cover-in transition-shadow duration-500"
          >
            <Cover id={track.id} url={track.cover_url} size={320} className="aspect-square w-full rounded-2xl" />
          </div>
          <div className="flex w-full max-w-xs items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                {p.playing && (
                  <span aria-label="Now playing" className="flex h-3 shrink-0 items-end gap-0.5">
                    {[0, 0.2, 0.4].map((d) => <i key={d} className="eq-bar block h-3 w-0.5 bg-accent" style={{ animationDelay: `${d}s` }} />)}
                  </span>
                )}
                <div data-testid="now-playing-title" className="truncate text-lg font-semibold">{track.title}</div>
              </div>
              <div className="truncate text-sm text-muted">{track.artist.name}</div>
            </div>
            <LikeButton trackId={track.id} />
          </div>

          <div className="w-full max-w-xs">
            <input
              aria-label="Seek"
              type="range"
              min={0}
              max={Math.max(duration, 1)}
              step={0.5}
              value={Math.min(p.currentTime, duration || 0)}
              onChange={(e) => p.requestSeek(Number(e.target.value))}
              className="h-1 w-full cursor-pointer"
            />
            <div className="flex justify-between font-mono text-xs tabular-nums text-muted">
              <span>{formatTime(p.currentTime)}</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>

          <div className="flex w-full max-w-xs items-center justify-between">
            <button
              aria-label={p.shuffle ? "Disable shuffle" : "Enable shuffle"}
              aria-pressed={p.shuffle}
              onClick={p.toggleShuffle}
              className={`flex size-11 items-center justify-center rounded-full active:scale-90 ${p.shuffle ? "text-accent" : "text-muted hover:text-fg"}`}
            >
              <ShuffleIcon />
            </button>
            <button aria-label="Previous" onClick={p.prev} className="flex size-14 items-center justify-center rounded-full text-fg active:scale-90">
              <PrevIcon width={28} height={28} />
            </button>
            <button
              aria-label={p.playing ? "Pause" : "Play"}
              onClick={p.toggle}
              className="flex size-[72px] items-center justify-center rounded-full bg-fg text-ink transition-transform active:scale-95"
            >
              {p.playing ? <PauseIcon width={32} height={32} /> : <PlayIcon width={32} height={32} />}
            </button>
            <button aria-label="Next" onClick={p.next} disabled={!hasNext} className="flex size-14 items-center justify-center rounded-full text-fg disabled:opacity-30 active:scale-90">
              <NextIcon width={28} height={28} />
            </button>
            <button
              aria-label={`Repeat: ${p.repeatMode}`}
              aria-pressed={p.repeatMode !== "off"}
              onClick={p.cycleRepeat}
              className={`flex size-11 items-center justify-center rounded-full active:scale-90 ${p.repeatMode !== "off" ? "text-accent" : "text-muted hover:text-fg"}`}
            >
              {p.repeatMode === "one" ? <RepeatOnceIcon /> : <RepeatIcon />}
            </button>
          </div>

          <div className="flex w-full max-w-xs items-center justify-center gap-10 pt-2">
            <button aria-label="Similar tracks" title="Similar tracks" onClick={() => p.setSimilarOpen(true)} className="flex size-11 items-center justify-center rounded-full text-muted hover:text-fg active:scale-90">
              <SimilarIcon />
            </button>
            <button aria-label="Queue" title="Queue" onClick={() => p.setQueueOpen(true)} className="flex size-11 items-center justify-center rounded-full text-muted hover:text-fg active:scale-90">
              <QueueIcon />
            </button>
          </div>
        </div>
      </div>

      {/* Lyrics: inline, reached by scrolling - not a separate screen (see file comment) */}
      <div className="flex-1 border-t border-line px-6 py-6">
        <h2 className="mb-4 text-lg font-semibold">Lyrics</h2>
        <LyricsView trackId={track.id} active={open} />
      </div>
    </div>
  );
}
