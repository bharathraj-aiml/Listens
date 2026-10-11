"use client";

import Cover, { hue } from "@/components/Cover";
import { CaretDownIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon } from "@/components/icons";
import LyricsView from "@/components/LyricsView";
import SidePanel from "@/components/SidePanel";
import { hslToRgbTriplet, useDominantColor } from "@/lib/color";
import { formatTime } from "@/lib/format";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { useSlideIn } from "@/lib/useSlideIn";
import { useSwipe } from "@/lib/swipe";
import { currentTrack, usePlayer } from "@/store/player";

const FADE = "linear-gradient(to bottom, transparent 0, black 18%, black 74%, transparent 94%)";

/** Desktop: the right-hand side panel. Phone: a full-screen "liquid glass" lyrics view in the
 *  style of Apple Music - the cover blurred into an ambient background, big bold lines, frosted
 *  glass header and transport. Only one of the two is mounted, so lyrics are fetched once. */
export default function LyricsPanel() {
  const isPhone = useMediaQuery("(max-width: 767px)");
  return isPhone ? <GlassLyrics /> : <DesktopLyrics />;
}

function DesktopLyrics() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.lyricsOpen);
  const setOpen = usePlayer((s) => s.setLyricsOpen);

  return (
    <SidePanel
      open={open}
      onClose={() => setOpen(false)}
      title="Lyrics"
      subtitle={track?.title}
      testId="lyrics-panel"
      ariaLabel="Lyrics"
    >
      <div className="px-5 py-6">
        <LyricsView trackId={track?.id} active={open} />
      </div>
    </SidePanel>
  );
}

function GlassLyrics() {
  const track = usePlayer(currentTrack);
  const open = usePlayer((s) => s.lyricsOpen);
  const setOpen = usePlayer((s) => s.setLyricsOpen);
  const p = usePlayer();
  const { mounted, shown } = useSlideIn(open, 250);
  const headerSwipe = useSwipe({ onSwipeDown: () => setOpen(false) });
  const fallback = track ? hslToRgbTriplet(hue(track.id), 50, 30) : "20, 20, 30";
  const ambient = useDominantColor(track?.cover_url ?? null, fallback);

  if (!mounted || !track) return null;
  const duration = p.duration || (track.duration_ms ?? 0) / 1000;
  const progress = duration > 0 ? Math.min(100, (p.currentTime / duration) * 100) : 0;

  return (
    <div
      data-testid="lyrics-sheet"
      aria-label="Lyrics"
      aria-hidden={!open}
      className={`fixed inset-0 z-40 overflow-hidden bg-ink transition-[transform,opacity] duration-300 ease-out motion-reduce:transition-none ${shown ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"}`}
    >
      {/* ambient backdrop: the cover blown up and blurred, tinted by its dominant colour */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{ background: `radial-gradient(ellipse 120% 80% at 50% 0%, rgba(${ambient}, 0.9), rgba(${ambient}, 0.35) 55%, var(--color-ink))` }}
      />
      {track.cover_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          aria-hidden
          src={track.cover_url}
          alt=""
          className="absolute left-1/2 top-1/3 size-[140vmax] -translate-x-1/2 -translate-y-1/2 scale-110 object-cover opacity-50 blur-3xl saturate-150"
        />
      )}
      <div aria-hidden className="absolute inset-0 bg-black/30" />

      {/* frosted header */}
      <div
        onPointerDown={headerSwipe.onPointerDown}
        onPointerUp={headerSwipe.onPointerUp}
        className="absolute inset-x-0 top-0 z-10 flex justify-end px-4 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]"
      >
        <button
          aria-label="Close lyrics"
          onClick={() => setOpen(false)}
          className="glass flex size-11 items-center justify-center rounded-full text-white active:scale-90"
        >
          <CaretDownIcon />
        </button>
      </div>

      {/* lyrics scroll area, faded at both edges; big padding lets the first and last line reach the centre */}
      <div
        className="absolute inset-0 overflow-y-auto overscroll-contain px-7 py-[38vh]"
        style={{ maskImage: FADE, WebkitMaskImage: FADE }}
      >
        <LyricsView trackId={track.id} active={open} glass />
      </div>

      {/* frosted transport */}
      <div className="absolute inset-x-0 bottom-0 z-10 px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="glass rounded-[2rem] px-5 pb-3 pt-4">
          <div className="flex items-center gap-3">
            <Cover id={track.id} url={track.cover_url} size={44} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-white">{track.title}</div>
              <div className="truncate text-xs text-white/70">{track.artist.name}</div>
            </div>
          </div>
          <input
            aria-label="Seek"
            data-testid="lyrics-seek"
            type="range"
            min={0}
            max={Math.max(duration, 1)}
            step={0.5}
            value={Math.min(p.currentTime, duration || 0)}
            onChange={(e) => p.requestSeek(Number(e.target.value))}
            style={{ background: `linear-gradient(to right, rgba(255,255,255,0.9) ${progress}%, rgba(255,255,255,0.2) ${progress}%)` }}
            className="mt-3 block h-1 w-full cursor-pointer appearance-none rounded-full accent-white [&::-webkit-slider-thumb]:size-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-moz-range-thumb]:size-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-white"
          />
          <div className="mt-2 flex justify-between font-mono text-[11px] tabular-nums text-white/70">
            <span>{formatTime(p.currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
          <div className="flex items-center justify-center gap-8 pt-1">
            <button aria-label="Previous" onClick={p.prev} className="flex size-12 items-center justify-center rounded-full text-white active:scale-90">
              <PrevIcon width={26} height={26} />
            </button>
            <button
              aria-label={p.playing ? "Pause" : "Play"}
              onClick={p.toggle}
              className="flex size-14 items-center justify-center rounded-full bg-white text-ink active:scale-95"
            >
              {p.playing ? <PauseIcon width={28} height={28} /> : <PlayIcon width={28} height={28} />}
            </button>
            <button
              aria-label="Next"
              onClick={p.next}
              disabled={p.index + 1 >= p.queue.length}
              className="flex size-12 items-center justify-center rounded-full text-white disabled:opacity-30 active:scale-90"
            >
              <NextIcon width={26} height={26} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
