"use client";

import { useEffect, useState } from "react";

/** HSL -> an "r, g, b" triplet string, so a deterministic hue-based fallback color can be
 *  combined with rgba()/opacity the same way as useDominantColor's sampled result below - no
 *  mixing hsl()/rgb() function syntax, which can't share an alpha suffix. */
export function hslToRgbTriplet(h: number, s: number, l: number): string {
  s /= 100;
  l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const round = (x: number) => Math.round(255 * x);
  return `${round(f(0))}, ${round(f(8))}, ${round(f(4))}`;
}

/** Samples a downscaled copy of a cover image to estimate its average color, for an ambient
 *  background wash on NowPlayingSheet (the same idea as Spotify/Apple Music's Now Playing
 *  screen, just an average rather than a proper palette extraction - good enough for a soft
 *  gradient backdrop). Cover URLs are same-origin (served through the gateway), so canvas
 *  pixel access works without a CORS error; anything that does fail - load error, a browser
 *  that blocks canvas reads, no cover at all - falls back to the caller's fallback "r, g, b"
 *  triplet. Returns a plain "r, g, b" triplet (no wrapping rgb(...)), so callers can drop it
 *  straight into their own rgba(${triplet}, alpha). */
export function useDominantColor(url: string | null, fallback: string): string {
  const [color, setColor] = useState(fallback);

  useEffect(() => {
    if (!url) {
      setColor(fallback);
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      try {
        const size = 16;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          setColor(fallback);
          return;
        }
        ctx.drawImage(img, 0, 0, size, size);
        const { data } = ctx.getImageData(0, 0, size, size);
        let r = 0, g = 0, b = 0, n = 0;
        for (let i = 0; i < data.length; i += 4) {
          r += data[i];
          g += data[i + 1];
          b += data[i + 2];
          n++;
        }
        setColor(`${Math.round(r / n)}, ${Math.round(g / n)}, ${Math.round(b / n)}`);
      } catch {
        setColor(fallback); // e.g. a canvas-read restriction in a locked-down browser
      }
    };
    img.onerror = () => !cancelled && setColor(fallback);
    img.src = url;
    return () => {
      cancelled = true;
    };
  }, [url, fallback]);

  return color;
}
