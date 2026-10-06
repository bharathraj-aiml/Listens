export interface ArtistRef { id: string; name: string }
export interface AlbumRef { id: string; title: string }

export interface Track {
  id: string;
  title: string;
  artist: ArtistRef;
  album: AlbumRef | null;
  genre: string | null;
  license: string | null;
  status: "uploaded" | "processing" | "ready" | "failed";
  duration_ms: number | null;
  cover_url: string | null;
  error: string | null;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  username: string;
  display_name: string;
  bio: string | null;
}

export interface SearchResults {
  tracks: Track[];
  artists: ArtistRef[];
  albums: { id: string; title: string; artist: ArtistRef }[];
  playlists: { id: string; name: string; description: string | null; owner_id: string }[];
}
