"use client";

import { hslToRgbTriplet, useDominantColor } from "@/lib/color";
import { currentTrack, usePlayer } from "@/store/player";

/** Scales a sampled "r, g, b" so its brightest channel is at most 150: keeps muted text over the
 *  wash above 4.5:1 even for a near-white cover. */
const capBrightness = (triplet: string) => {
  const ch = triplet.split(",").map((n) => Number(n));
  const k = Math.min(1, 150 / Math.max(...ch, 1));
  return ch.map((n) => Math.round(n * k)).join(", ");
};

const hue = (id: string) => [...id].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 0);

/** Fixed colour wash behind the whole app, taken from the playing cover so the glass surfaces
 *  refract the music itself instead of a decorative gradient. Nothing playing: renders nothing
 *  and the neutral resting backdrop in globals.css shows. */
export default function AmbientBackdrop() {
  const track = usePlayer(currentTrack);
  const fallback = track ? hslToRgbTriplet(hue(track.id), 45, 32) : "40, 40, 50";
  const ambient = capBrightness(useDominantColor(track?.cover_url ?? null, fallback));
  if (!track) return null;

  return (
    <div
      key={ambient}
      aria-hidden
      className="animate-fade-in pointer-events-none fixed inset-0 -z-10"
      style={{
        background: `radial-gradient(70vmax 55vmax at 8% -8%, rgba(${ambient}, 0.42), transparent 62%), radial-gradient(60vmax 50vmax at 100% 105%, rgba(${ambient}, 0.26), transparent 62%)`,
      }}
    />
  );
}
