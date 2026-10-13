"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import TrackList from "@/components/TrackList";
import { get } from "@/lib/api";
import type { SearchResults } from "@/lib/types";

type Filter = "all" | "artist" | "album" | "genre" | "mood";
const FILTERS: { id: Filter; label: string; hint: string }[] = [
  { id: "all", label: "All", hint: "Search tracks, artists, albums, playlists" },
  { id: "artist", label: "Artist", hint: "Songs by an artist, e.g. Hariharan" },
  { id: "album", label: "Album", hint: "Songs on an album or film, e.g. Guru" },
  { id: "genre", label: "Genre", hint: "A genre, e.g. Soundtrack" },
  { id: "mood", label: "Mood", hint: "A mood, e.g. sad, happy, calm, chill" },
];
interface Facets { genres: { name: string; count: number }[]; moods: { id: string; name: string; query: string; count: number }[] }

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get("q") ?? "";
  const initialBy = params.get("by");
  const [q, setQ] = useState(initial);
  const [by, setBy] = useState<Filter>(FILTERS.some((f) => f.id === initialBy) ? (initialBy as Filter) : "all");
  const [facets, setFacets] = useState<Facets | null>(null);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Quick picks for the Genre and Mood filters: what is actually in the library (fetched once, when first needed).
  useEffect(() => {
    if ((by === "genre" || by === "mood") && !facets) {
      get<Facets>("/api/catalogue/search/facets").then(setFacets).catch(() => {});
    }
  }, [by, facets]);

  // Debounce: search 250 ms after the last keystroke, and keep ?q= in the URL (shareable, back-button friendly).
  useEffect(() => {
    const term = q.trim();
    const byParam = by === "all" ? "" : `&by=${by}`;
    if (!term) {
      setResults(null);
      router.replace(by === "all" ? "/search" : `/search?by=${by}`);
      return;
    }
    let stale = false;
    const t = setTimeout(() => {
      router.replace(`/search?q=${encodeURIComponent(term)}${byParam}`);
      get<SearchResults>(`/api/catalogue/search?q=${encodeURIComponent(term)}&limit=20${byParam}`)
        .then((r) => { if (!stale) { setResults(r); setError(null); } })
        .catch((e) => !stale && setError(e.message));
    }, 250);
    return () => { stale = true; clearTimeout(t); };
  }, [q, by, router]);

  const empty = results && !results.tracks.length && !results.artists.length && !results.albums.length && !results.playlists.length;

  return (
    <div className="space-y-6">
      <input
        autoFocus
        type="search"
        data-testid="search-input"
        aria-label="Search"
        placeholder={FILTERS.find((f) => f.id === by)!.hint}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full rounded-full border border-line bg-raise px-5 py-3 outline-none focus:border-accent"
      />
      <div role="group" aria-label="Search in" data-testid="search-filters" className="-mt-3 flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            aria-pressed={by === f.id}
            data-testid={`filter-${f.id}`}
            onClick={() => { setBy(f.id); setResults(null); }}
            className={`shrink-0 rounded-full border px-3.5 py-1.5 text-sm transition-colors ${by === f.id ? "border-accent bg-accent/15 text-fg" : "border-line text-muted hover:text-fg"}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {!q.trim() && (by === "genre" || by === "mood") && facets && (
        <div data-testid="filter-picks" className="-mt-2 flex flex-wrap gap-2">
          {(by === "mood"
            ? facets.moods.map((m) => ({ key: m.id, label: m.name, count: m.count, query: m.query }))
            : facets.genres.map((g) => ({ key: g.name, label: g.name, count: g.count, query: g.name }))
          ).map((c) => (
            <button key={c.key} type="button" onClick={() => setQ(c.query)} className="rounded-full border border-line bg-raise px-3.5 py-1.5 text-sm hover:border-accent">
              {c.label} <span className="text-muted">{c.count}</span>
            </button>
          ))}
        </div>
      )}
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
