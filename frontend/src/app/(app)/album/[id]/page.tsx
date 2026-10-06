"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import { get } from "@/lib/api";
import type { ArtistRef, Track } from "@/lib/types";

interface AlbumDetail { id: string; title: string; artist: ArtistRef; tracks: Track[] }

export default function AlbumPage() {
  const { id } = useParams<{ id: string }>();
  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<AlbumDetail>(`/api/catalogue/albums/${id}`).then(setAlbum).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p role="alert" className="text-danger">{error}</p>;
  if (!album) return <p className="text-muted">Loading…</p>;
  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <h1 data-testid="page-title" className="text-3xl font-semibold tracking-tight">{album.title}</h1>
        <Link href={`/artist/${album.artist.id}`} className="text-sm text-muted hover:text-fg hover:underline">{album.artist.name}</Link>
        <div><PlayAllButton tracks={album.tracks} /></div>
      </header>
      <TrackList tracks={album.tracks} />
    </div>
  );
}
