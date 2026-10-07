import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ArtistRef(BaseModel):
    id: uuid.UUID
    name: str


class AlbumRef(BaseModel):
    id: uuid.UUID
    title: str


class UserRef(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str


class TrackOut(BaseModel):
    id: uuid.UUID
    title: str
    artist: ArtistRef
    album: AlbumRef | None
    genre: str | None
    license: str | None
    status: str
    duration_ms: int | None
    cover_url: str | None
    error: str | None = None
    created_at: datetime


class UploadOut(BaseModel):
    track: TrackOut
    duplicate: bool


class ArtistDetail(BaseModel):
    id: uuid.UUID
    name: str
    bio: str | None
    followed: bool
    tracks: list[TrackOut]


class AlbumDetail(BaseModel):
    id: uuid.UUID
    title: str
    artist: ArtistRef
    tracks: list[TrackOut]


class AlbumHit(BaseModel):
    id: uuid.UUID
    title: str
    artist: ArtistRef


class PlaylistHit(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID


class SearchOut(BaseModel):
    tracks: list[TrackOut]
    artists: list[ArtistRef]
    albums: list[AlbumHit]
    playlists: list[PlaylistHit]


class LyricsOut(BaseModel):
    lyrics: str | None
    lyrics_synced: str | None


# ---------------------------------------------------------------- playlists

class PlaylistCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_public: bool = True
    is_collaborative: bool = False


class PlaylistUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_public: bool | None = None
    is_collaborative: bool | None = None


class PlaylistOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    is_public: bool
    is_collaborative: bool
    track_count: int
    cover_url: str | None  # the first track's cover, used as a collage-of-one placeholder
    created_at: datetime
    updated_at: datetime


class PlaylistTrackOut(BaseModel):
    id: int  # playlist_tracks row id (stable handle for reorder/remove; a track may appear twice)
    position: int
    added_by: uuid.UUID | None
    added_at: datetime
    track: TrackOut


class PlaylistDetailOut(PlaylistOut):
    tracks: list[PlaylistTrackOut]


class AddTrackIn(BaseModel):
    track_id: uuid.UUID


class ReorderIn(BaseModel):
    to_index: int = Field(ge=0)


# ---------------------------------------------------------------- likes / follows / plays

class PlayIn(BaseModel):
    track_id: uuid.UUID
