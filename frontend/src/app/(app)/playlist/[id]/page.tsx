"use client";

import Link from "next/link";
import { PageSkeleton } from "@/components/Loaders";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, get, post } from "@/lib/api";
import { CaretDownIcon, CaretUpIcon, EditIcon, PlayIcon, TrashIcon } from "@/components/icons";
import Cover from "@/components/Cover";
import LikeButton from "@/components/LikeButton";
import { formatDuration } from "@/lib/format";
import type { PlaylistDetail, PlaylistTrack } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { usePlayer } from "@/store/player";
import ArtistLinks from "@/components/ArtistLinks";

export default function PlaylistPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const me = useAuth((s) => s.user);
  const playQueue = usePlayer((s) => s.playQueue);
  const [pl, setPl] = useState<PlaylistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");

  const refresh = useCallback(
    () => get<PlaylistDetail>(`/api/catalogue/playlists/${id}`).then(setPl).catch((e) => setError(e.message)),
    [id],
  );
  useEffect(() => { refresh(); }, [refresh]);

  const isOwner = !!pl && !!me && pl.owner_id === me.id;
  const canEdit = isOwner || !!pl?.is_collaborative;

  async function move(pt: PlaylistTrack, toIndex: number) {
    if (!pl) return;
    const tracks = await post<PlaylistTrack[]>(`/api/catalogue/playlists/${pl.id}/tracks/${pt.id}/move`, { to_index: toIndex });
    setPl({ ...pl, tracks });
  }

  async function remove(pt: PlaylistTrack) {
    if (!pl) return;
    await api(`/api/catalogue/playlists/${pl.id}/tracks/${pt.id}`, { method: "DELETE" });
    refresh();
  }

  async function saveName() {
    if (!pl || !name.trim()) return;
    await api(`/api/catalogue/playlists/${pl.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
    setRenaming(false);
    refresh();
  }

  async function toggle(field: "is_public" | "is_collaborative") {
    if (!pl) return;
    await api(`/api/catalogue/playlists/${pl.id}`, { method: "PATCH", body: JSON.stringify({ [field]: !pl[field] }) });
    refresh();
  }

  async function del() {
    if (!pl || !confirm(`Delete "${pl.name}"? This can't be undone.`)) return;
    await api(`/api/catalogue/playlists/${pl.id}`, { method: "DELETE" });
    router.replace("/playlists");
  }

  if (error) return <p role="alert" className="text-danger">{error}</p>;
  if (!pl) return <PageSkeleton />;

  const ready = pl.tracks.filter((pt) => pt.track.status === "ready").map((pt) => pt.track);

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        {renaming ? (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveName()}
              data-testid="playlist-rename-input"
              className="rounded-lg border border-line bg-raise px-3 py-1.5 text-2xl font-semibold outline-none focus:border-accent"
            />
            <button onClick={saveName} data-testid="playlist-rename-save" className="rounded-full bg-accent px-3 py-1.5 text-sm font-semibold text-ink">Save</button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <h1 data-testid="page-title" className="text-3xl font-semibold tracking-tight">{pl.name}</h1>
            {isOwner && (
              <button
                aria-label="Rename playlist"
                data-testid="playlist-rename-toggle"
                onClick={() => { setName(pl.name); setRenaming(true); }}
                className="flex size-9 items-center justify-center rounded-full text-muted hover:text-fg"
              >
                <EditIcon width={16} height={16} />
              </button>
            )}
          </div>
        )}
        {pl.description && <p className="max-w-2xl text-sm text-muted">{pl.description}</p>}
        <p className="text-xs text-muted">
          {pl.track_count} track{pl.track_count === 1 ? "" : "s"}
          {pl.is_collaborative && " · Collaborative"}
          {!pl.is_public && " · Private"}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          {ready.length > 0 && (
            <button data-testid="play-all" onClick={() => playQueue(ready, 0)} className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-ink hover:brightness-110">
              <PlayIcon /> Play all
            </button>
          )}
          {isOwner && (
            <>
              <button data-testid="toggle-public" onClick={() => toggle("is_public")} className="rounded-full border border-line px-3 py-1.5 text-xs text-muted hover:text-fg">
                {pl.is_public ? "Make private" : "Make public"}
              </button>
              <button data-testid="toggle-collaborative" onClick={() => toggle("is_collaborative")} className="rounded-full border border-line px-3 py-1.5 text-xs text-muted hover:text-fg">
                {pl.is_collaborative ? "Make non-collaborative" : "Make collaborative"}
              </button>
              <button data-testid="delete-playlist" onClick={del} className="flex size-9 items-center justify-center rounded-full text-muted hover:text-danger">
                <TrashIcon width={16} height={16} />
              </button>
            </>
          )}
        </div>
      </header>

      {pl.tracks.length === 0 && (
        <div className="rounded-xl border border-dashed border-line p-8 text-center text-muted">
          No tracks yet. Add some from <Link href="/" className="text-accent underline">Home</Link> or <Link href="/search" className="text-accent underline">Search</Link>.
        </div>
      )}

      <ul data-testid="playlist-track-list" className="divide-y divide-line/60">
        {pl.tracks.map((pt, i) => (
          <li key={pt.id} data-testid="playlist-track-row" data-title={pt.track.title} className="group flex items-center gap-3 px-2 py-2 hover:bg-raise/40">
            <Cover id={pt.track.id} url={pt.track.cover_url} size={44} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">{pt.track.title}</div>
              <div className="truncate text-xs text-muted">
                <ArtistLinks track={pt.track} />
              </div>
            </div>
            <LikeButton trackId={pt.track.id} size={18} />
            <span className="hidden w-12 text-right font-mono text-xs tabular-nums text-muted sm:block">{formatDuration(pt.track.duration_ms)}</span>
            {canEdit && (
              <div className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100">
                <button aria-label="Move up" data-testid="move-up" disabled={i === 0} onClick={() => move(pt, i - 1)} className="flex size-9 items-center justify-center rounded-full text-muted hover:text-fg disabled:opacity-30">
                  <CaretUpIcon width={16} height={16} />
                </button>
                <button aria-label="Move down" data-testid="move-down" disabled={i === pl.tracks.length - 1} onClick={() => move(pt, i + 1)} className="flex size-9 items-center justify-center rounded-full text-muted hover:text-fg disabled:opacity-30">
                  <CaretDownIcon width={16} height={16} />
                </button>
                <button aria-label={`Remove ${pt.track.title}`} data-testid="remove-from-playlist" onClick={() => remove(pt)} className="flex size-9 items-center justify-center rounded-full text-muted hover:text-danger">
                  <TrashIcon width={16} height={16} />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
