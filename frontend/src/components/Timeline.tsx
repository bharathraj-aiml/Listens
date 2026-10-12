"use client";

import type { CSSProperties } from "react";
import { usePlayer } from "@/store/player";

interface Props {
  value: number;
  max: number;
  onSeek: (to: number) => void;
  tone?: "accent" | "light";
  testId?: string;
  ariaLabel?: string;
  className?: string;
}

/** The song's timeline. A real range input (keyboard, screen readers, tap-anywhere-to-seek all work) styled in
 *  globals.css: the played part fills with a smooth glide between position updates, the handle grows under a
 *  finger or cursor and softly pulses while the song plays, and the unplayed part sweeps while it buffers. */
export default function Timeline({ value, max, onSeek, tone = "accent", testId, ariaLabel = "Seek", className = "" }: Props) {
  const playing = usePlayer((s) => s.playing);
  const buffering = usePlayer((s) => s.buffering);
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;

  return (
    <input
      data-testid={testId}
      aria-label={ariaLabel}
      type="range"
      min={0}
      max={Math.max(max, 1)}
      step={0.5}
      value={Math.min(value, max || 0)}
      onChange={(e) => onSeek(Number(e.target.value))}
      data-playing={playing && !buffering}
      data-buffering={buffering}
      style={{ "--fill": `${pct}%` } as CSSProperties}
      className={`timeline ${tone === "light" ? "timeline-light" : ""} ${className}`}
    />
  );
}
