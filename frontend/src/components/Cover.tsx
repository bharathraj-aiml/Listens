function hue(id: string) {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/** Cover art, or a deterministic gradient placeholder when the track has none. */
export default function Cover({ id, url, size = 44, className = "" }: { id: string; url: string | null; size?: number; className?: string }) {
  const style = { width: size, height: size };
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" loading="lazy" style={style} className={`shrink-0 rounded-md object-cover ${className}`} />;
  }
  const h = hue(id);
  return (
    <div
      aria-hidden
      style={{ ...style, background: `linear-gradient(135deg, hsl(${h} 55% 35%), hsl(${(h + 60) % 360} 60% 22%))` }}
      className={`shrink-0 rounded-md ${className}`}
    />
  );
}
