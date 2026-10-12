"use client";

/** Loading states. Music-themed bars for waits, shimmering skeletons shaped like the content that is coming,
 *  so a page keeps its layout instead of jumping when the data arrives. Motion stops under reduced-motion. */

export function SoundBars({ size = 20, className = "", label = "Loading" }: { size?: number; className?: string; label?: string }) {
  return (
    <span role="status" aria-label={label} className={`sound-bars ${className}`} style={{ height: size }}>
      <i /><i /><i /><i /><i />
    </span>
  );
}

export function Skeleton({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div aria-hidden className={`skeleton ${className}`} style={style} />;
}

/** Full-screen centred loader: shown while the signed-in shell works out who you are. */
export function CenteredLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="grid min-h-dvh place-items-center">
      <div className="flex animate-fade-in flex-col items-center gap-4">
        <SoundBars size={36} label={label} />
        <span className="text-sm text-muted">{label}</span>
      </div>
    </div>
  );
}

/** Rows shaped like TrackList rows: cover, two text lines, and two action buttons. */
export function TrackRowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" role="status" className="divide-y divide-line/60">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2">
          <Skeleton className="size-11 shrink-0 rounded-md" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 rounded" style={{ width: `${55 + ((i * 17) % 30)}%` }} />
            <Skeleton className="h-3 rounded" style={{ width: `${30 + ((i * 11) % 25)}%` }} />
          </div>
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <Skeleton className="size-8 shrink-0 rounded-full" />
        </div>
      ))}
    </div>
  );
}

/** Album/playlist-style grid: 150px cover cards with a title and a subtitle. */
export function AlbumGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" role="status" className="flex flex-wrap gap-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="w-[150px] space-y-2">
          <Skeleton className="size-[150px] rounded-lg" />
          <Skeleton className="h-3.5 rounded" style={{ width: `${60 + ((i * 13) % 30)}%` }} />
          <Skeleton className="h-3 w-3/5 rounded" />
        </div>
      ))}
    </div>
  );
}

/** Detail page (album, artist, playlist): a title block over a track list. */
export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" role="status" className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-8 w-2/3 max-w-md rounded-lg" />
        <Skeleton className="h-4 w-1/3 max-w-xs rounded" />
        <Skeleton className="h-10 w-28 rounded-full" />
      </div>
      <TrackRowsSkeleton rows={rows} />
    </div>
  );
}

/** Lyrics: a few lines of varied length. `glass` is the white-on-colour full-screen variant. */
export function LyricsSkeleton({ glass = false }: { glass?: boolean }) {
  return (
    <div aria-busy="true" aria-label="Loading lyrics" role="status" className={glass ? "space-y-7" : "space-y-4"}>
      {[86, 64, 78, 52, 70, 44].map((w, i) => (
        <Skeleton key={i} className={`${glass ? "h-7 bg-white/15" : "h-4"} rounded-lg`} style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}
