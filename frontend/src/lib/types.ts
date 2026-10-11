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
  tempo_bpm?: number | null; // audio analysis, used by the shuffle to order songs for flow
  energy?: number | null;
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

export interface TopArtist {
  artist: ArtistRef;
  play_count: number;
}

export interface ListeningStats {
  range: "this_week" | "last_week";
  start: string;
  end: string;
  top_artist: TopArtist | null;
  top_track: TopTrack | null;
}

export interface AlbumCard {
  id: string;
  title: string;
  artist: ArtistRef;
  cover_url: string | null;
  track_count: number;
}

export interface RecentsDay {
  day: string;
  play_count: number;
  cover_track: Track | null;
}
