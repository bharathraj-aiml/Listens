"use client";

import { useEffect, useRef, useState } from "react";
import { PlaylistIcon } from "@/components/icons";
import { get, post } from "@/lib/api";
import type { Playlist } from "@/lib/types";

export default function AddToPlaylistMenu({ trackId, trackTitle }: { trackId: string; trackTitle: string }) {
  const [open, setOpen] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    get<Playlist[]>("/api/catalogue/playlists/mine").then(setPlaylists).catch(() => setPlaylists([]));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function addTo(playlistId: string) {
    try {
      await post(`/api/catalogue/playlists/${playlistId}/tracks`, { track_id: trackId });
      setAdded(playlistId);
      setTimeout(() => setOpen(false), 700);
    } catch {
      /* the menu just stays open so the user can try another playlist */
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        aria-label={`Add ${trackTitle} to a playlist`}
        data-testid="add-to-playlist"
        onClick={(e) => {
          e.stopPropagation();
          setAdded(null);
          setOpen((o) => !o);
        }}
        className="flex size-9 items-center justify-center rounded-full text-muted hover:text-fg"
      >
        <PlaylistIcon width={18} height={18} />
      </button>
      {open && (
        <div data-testid="add-to-playlist-menu" className="glass-surface absolute right-0 top-full z-50 mt-1 w-56 rounded-xl p-1">
          {playlists === null && <div className="px-3 py-2 text-xs text-muted">Loading…</div>}
          {playlists?.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted">No playlists yet. Create one from the Playlists page.</div>
          )}
          {playlists?.map((p) => (
            <button
              key={p.id}
              data-testid="add-to-playlist-option"
              onClick={() => addTo(p.id)}
              className="flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm hover:bg-white/10"
            >
              <span className="truncate">{p.name}</span>
              {added === p.id && <span className="text-xs text-ok">Added</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
