"use client";

import { hslToRgbTriplet, useDominantColor } from "@/lib/color";
import { currentTrack, usePlayer } from "@/store/player";

/** Turns a sampled "r, g, b" into the colour the glass refracts. A plain average of a cover is usually a
 *  muddy grey-brown, so saturation is lifted (glass needs colour to show), then brightness is capped:
 *  the brightest channel stays at or below 150 so muted text over the wash stays above 4.5:1 even for a
 *  near-white cover. */
const tint = (triplet: string) => {
  const [r, g, b] = triplet.split(",").map((n) => Number(n) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const mid = (max + min) / 2;
  const boosted = [r, g, b].map((c) => Math.min(1, Math.max(0, mid + (c - mid) * 1.7)));
  const k = Math.min(1, 150 / (Math.max(...boosted) * 255 || 1));
  return boosted.map((c) => Math.round(c * 255 * k)).join(", ");
};

const hue = (id: string) => [...id].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 0);

/** Fixed colour wash behind the whole app, taken from the playing cover so the glass surfaces
 *  refract the music itself instead of a decorative gradient. Nothing playing: renders nothing
 *  and the neutral resting backdrop in globals.css shows. */
export default function AmbientBackdrop() {
  const track = usePlayer(currentTrack);
  const fallback = track ? hslToRgbTriplet(hue(track.id), 45, 32) : "40, 40, 50";
  const ambient = tint(useDominantColor(track?.cover_url ?? null, fallback));
  if (!track) return null;

  return (
    <div
      key={ambient}
      aria-hidden
      className="animate-fade-in pointer-events-none fixed inset-0 -z-10"
      style={{
        background: `radial-gradient(70vmax 60vmax at 6% -6%, rgba(${ambient}, 0.55), transparent 62%), radial-gradient(55vmax 45vmax at 100% 40%, rgba(${ambient}, 0.28), transparent 62%), radial-gradient(70vmax 50vmax at 40% 112%, rgba(${ambient}, 0.38), transparent 62%)`,
      }}
    />
  );
}
