"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import { get } from "@/lib/api";
import type { Track } from "@/lib/types";

interface ArtistDetail { id: string; name: string; bio: string | null; tracks: Track[] }

export default function ArtistPage() {
  const { id } = useParams<{ id: string }>();
  const [artist, setArtist] = useState<ArtistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<ArtistDetail>(`/api/catalogue/artists/${id}`).then(setArtist).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p role="alert" className="text-danger">{error}</p>;
  if (!artist) return <p className="text-muted">Loading…</p>;
  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <h1 data-testid="page-title" className="text-3xl font-semibold tracking-tight">{artist.name}</h1>
        {artist.bio && <p className="max-w-2xl text-sm text-muted">{artist.bio}</p>}
        <PlayAllButton tracks={artist.tracks} />
      </header>
      <TrackList tracks={artist.tracks} />
    </div>
  );
}
