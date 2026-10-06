import uuid
from datetime import datetime

from pydantic import BaseModel


class ArtistRef(BaseModel):
    id: uuid.UUID
    name: str


class AlbumRef(BaseModel):
    id: uuid.UUID
    title: str


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
