"use client";

import Link from "next/link";
import { TrackRowsSkeleton } from "@/components/Loaders";
import { useEffect, useState } from "react";
import Cover from "@/components/Cover";
import { PlusIcon } from "@/components/icons";
import { get, post } from "@/lib/api";
import type { Playlist } from "@/lib/types";
import { usePlayer } from "@/store/player";

export default function PlaylistsPage() {
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const defaultPlaylistPublic = usePlayer((s) => s.defaultPlaylistPublic);

  const refresh = () => get<Playlist[]>("/api/catalogue/playlists/mine").then(setPlaylists).catch((e) => setError(e.message));
  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      // Visibility default comes from Settings -> Privacy and social (see store/player.ts).
      await post("/api/catalogue/playlists", { name: name.trim(), is_public: defaultPlaylistPublic, is_collaborative: false });
      setName("");
      setCreating(false);
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Playlists</h1>
        <button
          data-testid="new-playlist-toggle"
          onClick={() => setCreating((c) => !c)}
          className="inline-flex items-center gap-1 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-ink hover:brightness-110"
        >
          <PlusIcon width={16} height={16} /> New playlist
        </button>
      </header>

      {creating && (
        <form onSubmit={create} data-testid="new-playlist-form" className="glass-card flex gap-2 rounded-2xl border border-line bg-panel p-3">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Playlist name"
            data-testid="new-playlist-name"
            className="flex-1 rounded-lg border border-line bg-raise px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button type="submit" disabled={busy || !name.trim()} data-testid="new-playlist-submit" className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-ink disabled:opacity-40">
            Create
          </button>
        </form>
      )}

      {error && <p role="alert" className="text-danger">{error}</p>}
      {playlists === null && !error && <TrackRowsSkeleton rows={4} />}
      {playlists && playlists.length === 0 && (
        <div className="rounded-xl border border-dashed border-line p-8 text-center text-muted">No playlists yet. Create one to get started.</div>
      )}
      {playlists && playlists.length > 0 && (
        <ul data-testid="playlist-list" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {playlists.map((p) => (
            <li key={p.id}>
              <Link href={`/playlist/${p.id}`} data-testid="playlist-card" className="glass-card flex items-center gap-3 rounded-2xl border border-line bg-panel p-3 transition-colors hover:border-accent hover:bg-raise">
                <Cover id={p.id} url={p.cover_url} size={56} />
                <div className="min-w-0">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="text-xs text-muted">
                    {p.track_count} track{p.track_count === 1 ? "" : "s"}
                    {p.is_collaborative && " · Collaborative"}
                    {!p.is_public && " · Private"}
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
