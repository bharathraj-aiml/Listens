"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import TrackList from "@/components/TrackList";
import { get } from "@/lib/api";
import type { SearchResults } from "@/lib/types";

function SearchInner() {
  const router = useRouter();
  const initial = useSearchParams().get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Debounce: search 250 ms after the last keystroke, and keep ?q= in the URL (shareable, back-button friendly).
  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults(null);
      router.replace("/search");
      return;
    }
    let stale = false;
    const t = setTimeout(() => {
      router.replace(`/search?q=${encodeURIComponent(term)}`);
      get<SearchResults>(`/api/catalogue/search?q=${encodeURIComponent(term)}&limit=20`)
        .then((r) => { if (!stale) { setResults(r); setError(null); } })
        .catch((e) => !stale && setError(e.message));
    }, 250);
    return () => { stale = true; clearTimeout(t); };
  }, [q, router]);

  const empty = results && !results.tracks.length && !results.artists.length && !results.albums.length && !results.playlists.length;

  return (
    <div className="space-y-6">
      <input
        autoFocus
        type="search"
        data-testid="search-input"
        aria-label="Search"
        placeholder="Search tracks, artists, albums, playlists"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full rounded-full border border-line bg-raise px-5 py-3 outline-none focus:border-accent"
      />
      {error && <p role="alert" className="text-danger">{error}</p>}
      {empty && <p className="text-muted" data-testid="no-results">No results for “{q.trim()}”.</p>}
      {results && results.tracks.length > 0 && (
        <section><h2 className="mb-2 text-lg font-medium">Tracks</h2><TrackList tracks={results.tracks} /></section>
      )}
      {results && results.artists.length > 0 && (
        <section data-testid="artist-results">
          <h2 className="mb-2 text-lg font-medium">Artists</h2>
          <ul className="flex flex-wrap gap-2">
            {results.artists.map((a) => (
              <li key={a.id}><Link href={`/artist/${a.id}`} className="block rounded-full border border-line bg-raise px-4 py-2 text-sm hover:border-accent">{a.name}</Link></li>
            ))}
          </ul>
        </section>
      )}
      {results && results.albums.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-medium">Albums</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {results.albums.map((a) => (
              <li key={a.id}><Link href={`/album/${a.id}`} className="block rounded-lg border border-line bg-raise px-4 py-3 text-sm hover:border-accent">
                <div className="font-medium">{a.title}</div><div className="text-xs text-muted">{a.artist.name}</div>
              </Link></li>
            ))}
          </ul>
        </section>
      )}
      {results && results.playlists.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-medium">Playlists</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {results.playlists.map((p) => (
              <li key={p.id} className="rounded-lg border border-line bg-raise px-4 py-3 text-sm">
                <div className="font-medium">{p.name}</div>{p.description && <div className="text-xs text-muted">{p.description}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default function SearchPage() {
  // useSearchParams() needs a Suspense boundary for static prerendering.
  return <Suspense fallback={null}><SearchInner /></Suspense>;
}
