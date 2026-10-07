"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import FollowButton from "@/components/FollowButton";
import TrackList, { PlayAllButton } from "@/components/TrackList";
import { get } from "@/lib/api";
import type { ArtistDetail } from "@/lib/types";

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
        <div className="flex items-center gap-3">
          <PlayAllButton tracks={artist.tracks} />
          <FollowButton artistId={artist.id} initialFollowed={artist.followed} />
        </div>
      </header>
      <TrackList tracks={artist.tracks} />
    </div>
  );
}
