"use client";

import { usePlayer, type Quality } from "@/store/player";

const LABELS: Record<number, string> = { 96: "96 kbps · data saver", 160: "160 kbps · normal", 320: "320 kbps · best" };

/** Quality picker. Options are the renditions the current track actually offers (a low-bitrate
 *  source has no 320 kbps rendition). Hidden when playing via native HLS (Safari), which can't switch. */
export default function QualitySelect({ className = "" }: { className?: string }) {
  const quality = usePlayer((s) => s.quality);
  const levels = usePlayer((s) => s.levels);
  const setQuality = usePlayer((s) => s.setQuality);
  if (!levels.length) return null;
  return (
    <label className={`flex items-center gap-2 text-xs text-muted ${className}`}>
      <span className="sr-only md:not-sr-only">Quality</span>
      <select
        data-testid="quality-select"
        value={String(quality)}
        onChange={(e) => setQuality((e.target.value === "auto" ? "auto" : Number(e.target.value)) as Quality)}
        className="rounded-md border border-line bg-raise px-2 py-1 text-fg"
      >
        <option value="auto">Auto</option>
        {levels.map((k) => (
          <option key={k} value={k}>{LABELS[k] ?? `${k} kbps`}</option>
        ))}
      </select>
    </label>
  );
}
