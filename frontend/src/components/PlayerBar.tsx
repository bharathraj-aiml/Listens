"use client";

import Link from "next/link";
import Cover from "@/components/Cover";
import { MuteIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, QueueIcon, VolumeIcon } from "@/components/icons";
import QualitySelect from "@/components/QualitySelect";
import { formatTime } from "@/lib/format";
import { currentTrack, usePlayer } from "@/store/player";

/** Persistent mini-player: lives in the (app) layout so it stays put (and keeps playing) across pages. */
export default function PlayerBar() {
  const track = usePlayer(currentTrack);
  const p = usePlayer();
  if (!track) return null;
  const duration = p.duration || (track.duration_ms ?? 0) / 1000;
  const hasNext = p.index + 1 < p.queue.length;

  return (
    <div
      data-testid="player-bar"
      className="fixed inset-x-0 bottom-14 z-30 border-t border-line bg-panel/95 backdrop-blur md:bottom-0 md:left-60"
    >
      {/* thin progress line on mobile (the full slider is desktop-only) */}
      <div className="h-0.5 bg-line md:hidden">
        <div className="h-full bg-accent" style={{ width: duration ? `${Math.min(100, (p.currentTime / duration) * 100)}%` : 0 }} />
      </div>
      <div className="mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-3 px-3 py-2 md:grid-cols-[1fr_minmax(320px,2fr)_1fr] md:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Cover id={track.id} url={track.cover_url} size={44} />
          <div className="min-w-0">
            <div data-testid="now-title" className="truncate text-sm font-medium">{track.title}</div>
            <Link href={`/artist/${track.artist.id}`} className="block truncate text-xs text-muted hover:text-fg hover:underline">
              {track.artist.name}
            </Link>
            {p.error && <div role="alert" data-testid="player-error" className="truncate text-xs text-danger">{p.error}</div>}
          </div>
        </div>

        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-1">
            <button data-testid="prev" aria-label="Previous" onClick={p.prev} className="rounded-full p-2 text-muted hover:text-fg">
              <PrevIcon />
            </button>
            <button
              data-testid="play-toggle"
              aria-label={p.playing ? "Pause" : "Play"}
              onClick={p.toggle}
              className="rounded-full bg-fg p-2.5 text-ink hover:scale-105 active:scale-95"
            >
              {p.playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <button data-testid="next" aria-label="Next" onClick={p.next} disabled={!hasNext} className="rounded-full p-2 text-muted hover:text-fg disabled:opacity-30">
              <NextIcon />
            </button>
            <button aria-label="Queue" data-testid="queue-toggle" onClick={() => p.setQueueOpen(true)} className="rounded-full p-2 text-muted hover:text-fg md:hidden">
              <QueueIcon />
            </button>
          </div>
          <div className="hidden w-full items-center gap-2 text-xs tabular-nums text-muted md:flex">
            <span data-testid="time-current" className="w-10 text-right">{formatTime(p.currentTime)}</span>
            <input
              data-testid="seek"
              aria-label="Seek"
              type="range"
              min={0}
              max={Math.max(duration, 1)}
              step={0.5}
              value={Math.min(p.currentTime, duration || 0)}
              onChange={(e) => p.requestSeek(Number(e.target.value))}
              className="h-1 flex-1 cursor-pointer"
            />
            <span data-testid="time-total" className="w-10">{formatTime(duration)}</span>
          </div>
        </div>

        <div className="hidden items-center justify-end gap-3 md:flex">
          <QualitySelect />
          <button aria-label={p.muted ? "Unmute" : "Mute"} onClick={p.toggleMute} className="text-muted hover:text-fg">
            {p.muted || p.volume === 0 ? <MuteIcon /> : <VolumeIcon />}
          </button>
          <input
            data-testid="volume"
            aria-label="Volume"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={p.muted ? 0 : p.volume}
            onChange={(e) => p.setVolume(Number(e.target.value))}
            className="h-1 w-24 cursor-pointer"
          />
          <button aria-label="Queue" data-testid="queue-toggle-desktop" onClick={() => p.setQueueOpen(!p.queueOpen)} className={`rounded-full p-2 hover:text-fg ${p.queueOpen ? "text-accent" : "text-muted"}`}>
            <QueueIcon />
          </button>
        </div>
      </div>
    </div>
  );
}
