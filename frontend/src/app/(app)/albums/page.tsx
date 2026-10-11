"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Cover from "@/components/Cover";
import { get } from "@/lib/api";
import type { AlbumCard } from "@/lib/types";

export default function AlbumsPage() {
  const [albums, setAlbums] = useState<AlbumCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<AlbumCard[]>("/api/catalogue/albums").then(setAlbums).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Albums</h1>
        <p className="text-sm text-muted">Grouped automatically from each track&apos;s album tag.</p>
      </header>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {albums === null && !error && <p className="text-muted">Loading…</p>}
      {albums && albums.length === 0 && (
        <div className="rounded-xl border border-dashed border-line p-8 text-center text-muted">
          No albums yet. Tracks with the same album tag (an OST, an EP, a movie soundtrack) will group here automatically.
        </div>
      )}
      {albums && albums.length > 0 && (
        <div className="flex flex-wrap gap-4">
          {albums.map((a) => (
            <Link key={a.id} href={`/album/${a.id}`} className="group w-[150px]">
              <Cover id={a.id} url={a.cover_url} size={150} className="rounded-lg transition-transform group-hover:scale-[1.02]" />
              <div className="mt-2 truncate text-sm font-medium">{a.title}</div>
              <div className="truncate text-xs text-muted">{a.artist.name} · {a.track_count} track{a.track_count === 1 ? "" : "s"}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
