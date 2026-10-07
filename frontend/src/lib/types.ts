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

export interface UserRef {
  id: string;
  username: string;
  display_name: string;
}

export interface SearchResults {
  tracks: Track[];
  artists: ArtistRef[];
  albums: { id: string; title: string; artist: ArtistRef }[];
  playlists: { id: string; name: string; description: string | null; owner_id: string }[];
}

export interface Playlist {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  is_public: boolean;
  is_collaborative: boolean;
  track_count: number;
  cover_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaylistTrack {
  id: number;
  position: number;
  added_by: string | null;
  added_at: string;
  track: Track;
}

export interface PlaylistDetail extends Playlist {
  tracks: PlaylistTrack[];
}

export interface ArtistDetail {
  id: string;
  name: string;
  bio: string | null;
  followed: boolean;
  tracks: Track[];
}

export interface Lyrics {
  lyrics: string | null;
  lyrics_synced: string | null;
}

export interface TopTrack {
  track: Track;
  stream_count: number;
}

export interface SkipRateEntry {
  track: Track;
  play_count: number;
  skip_count: number;
  skip_rate: number;
}

export interface HourBucket {
  hour: number;
  count: number;
}
