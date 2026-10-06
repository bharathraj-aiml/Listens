import hashlib
import logging
import os
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import Album, Artist, Track
from listens_common.storage import delete_prefix, get_s3
from listens_common.web import current_user_id, get_redis

from . import search as search_mod
from .schemas import (
    AlbumDetail, AlbumHit, AlbumRef, ArtistDetail, ArtistRef, PlaylistHit, SearchOut, TrackOut, UploadOut,
)
from .serialize import track_out
from .tags import read_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("catalogue")

app = FastAPI(title="Shadow Listens - Catalogue", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

TRANSCODE_STREAM = "jobs:transcode"
ALLOWED_EXT = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac"}
CHUNK = 1024 * 1024


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------- upload

def _find_or_create_artist(db: Session, user_id: uuid.UUID, name: str) -> Artist:
    artist = db.scalar(
        select(Artist).where(Artist.owner_user_id == user_id, func.lower(Artist.name) == name.lower())
    )
    if artist is None:
        artist = Artist(name=name, owner_user_id=user_id)
        db.add(artist)
        db.flush()
    return artist


def _find_or_create_album(db: Session, artist: Artist, title: str) -> Album:
    album = db.scalar(select(Album).where(Album.artist_id == artist.id, func.lower(Album.title) == title.lower()))
    if album is None:
        album = Album(artist_id=artist.id, title=title)
        db.add(album)
        db.flush()
    return album


@app.get("/uploads/exists")
def upload_exists(
    sha256: str = Query(pattern=r"^[0-9a-fA-F]{64}$"),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Lets the import script skip files it already uploaded without re-sending 2.5 GB."""
    track_id = db.scalar(
        select(Track.id).where(Track.uploader_id == user_id, Track.content_sha256 == sha256.lower())
    )
    return {"exists": track_id is not None, "track_id": track_id}


@app.post("/upload", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def upload(
    response: Response,
    file: UploadFile = File(...),
    license: str = Form(..., min_length=2, max_length=100),
    rights_confirmed: bool = Form(...),
    title: str | None = Form(None, max_length=200),
    artist: str | None = Form(None, max_length=200),
    album: str | None = Form(None, max_length=200),
    genre: str | None = Form(None, max_length=60),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    r: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> UploadOut:
    # Sync endpoint on purpose: FastAPI runs it in a threadpool, so the blocking hashing and
    # S3 upload below don't stall the event loop.
    if not rights_confirmed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You must confirm you own the rights to this audio")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type; allowed: {sorted(ALLOWED_EXT)}")

    # Hash while measuring size (the body is already spooled to a temp file by Starlette).
    sha, size, limit = hashlib.sha256(), 0, settings.max_upload_mb * 1024 * 1024
    while chunk := file.file.read(CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
        sha.update(chunk)
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    digest = sha.hexdigest()

    existing = db.scalar(select(Track).where(Track.uploader_id == user_id, Track.content_sha256 == digest))
    if existing:
        response.status_code = status.HTTP_200_OK
        return UploadOut(track=track_out(existing, settings, user_id), duplicate=True)

    tags = read_tags(file.file)
    stem = os.path.splitext(os.path.basename(file.filename or "Untitled"))[0]
    # Explicit form values win over embedded tags, which win over filename/"Unknown Artist".
    final_title = (title or tags.get("title") or stem).strip()[:200]
    artist_row = _find_or_create_artist(db, user_id, (artist or tags.get("artist") or "Unknown Artist").strip()[:200])
    album_name = album or tags.get("album")
    album_row = _find_or_create_album(db, artist_row, album_name.strip()[:200]) if album_name else None

    track_id = uuid.uuid4()
    source_key = f"originals/{track_id}/source{ext}"
    file.file.seek(0)
    s3 = get_s3()
    s3.upload_fileobj(file.file, settings.s3_bucket_audio, source_key)
    track = Track(
        id=track_id, artist_id=artist_row.id, album_id=album_row.id if album_row else None, uploader_id=user_id,
        title=final_title, genre=(genre or tags.get("genre") or None), license=license.strip(),
        status="uploaded", source_key=source_key, content_sha256=digest,
    )
    db.add(track)
    try:
        db.commit()
    except Exception:
        db.rollback()
        s3.delete_object(Bucket=settings.s3_bucket_audio, Key=source_key)
        raise
    # If this enqueue is lost (Redis down), the worker's periodic sweep re-queues stuck 'uploaded' tracks.
    try:
        r.xadd(TRANSCODE_STREAM, {"track_id": str(track_id), "attempt": "0"})
    except Exception:
        log.exception("could not enqueue transcode job for %s; the worker sweep will pick it up", track_id)
    db.refresh(track)
    log.info("uploaded track %s (%d bytes) by %s", track_id, size, user_id)
    return UploadOut(track=track_out(track, settings, user_id), duplicate=False)


# ---------------------------------------------------------------- tracks

def _tracks_query():
    return select(Track).order_by(Track.created_at.desc(), Track.id)


@app.get("/tracks", response_model=list[TrackOut])
def list_tracks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    rows = db.scalars(_tracks_query().where(Track.status == "ready").limit(limit).offset(offset)).unique()
    return [track_out(t, settings, user_id) for t in rows]


@app.get("/tracks/mine", response_model=list[TrackOut])
def my_tracks(
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    """Everything the caller uploaded, including processing/failed (drives the upload page)."""
    rows = db.scalars(_tracks_query().where(Track.uploader_id == user_id).limit(500)).unique()
    return [track_out(t, settings, user_id) for t in rows]


def _get_track(db: Session, track_id: uuid.UUID) -> Track:
    track = db.get(Track, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return track


@app.get("/tracks/{track_id}", response_model=TrackOut)
def get_track(
    track_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrackOut:
    track = _get_track(db, track_id)
    if track.status != "ready" and track.uploader_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return track_out(track, settings, user_id)


@app.delete("/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_track(
    track_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    track = _get_track(db, track_id)
    if track.uploader_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the uploader can delete a track")
    s3 = get_s3()
    cover_key = track.cover_key
    db.delete(track)
    db.commit()
    delete_prefix(s3, settings.s3_bucket_audio, f"originals/{track_id}/")
    delete_prefix(s3, settings.s3_bucket_audio, f"hls/{track_id}/")
    if cover_key:
        s3.delete_object(Bucket=settings.s3_bucket_covers, Key=cover_key)


# ---------------------------------------------------------------- artists / albums

@app.get("/artists/{artist_id}", response_model=ArtistDetail)
def get_artist(
    artist_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ArtistDetail:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    tracks = db.scalars(_tracks_query().where(Track.artist_id == artist_id, Track.status == "ready")).unique()
    return ArtistDetail(
        id=artist.id, name=artist.name, bio=artist.bio, tracks=[track_out(t, settings, user_id) for t in tracks]
    )


@app.get("/albums/{album_id}", response_model=AlbumDetail)
def get_album(
    album_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AlbumDetail:
    album = db.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")
    artist = db.get(Artist, album.artist_id)
    # No track-number column yet, so order by upload time then title.
    tracks = db.scalars(
        select(Track).where(Track.album_id == album_id, Track.status == "ready").order_by(Track.created_at, Track.title)
    ).unique()
    return AlbumDetail(
        id=album.id, title=album.title, artist=ArtistRef(id=artist.id, name=artist.name),
        tracks=[track_out(t, settings, user_id) for t in tracks],
    )


# ---------------------------------------------------------------- search

@app.get("/search", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=50),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SearchOut:
    hits = search_mod.search(db, q.strip(), user_id, limit)
    return SearchOut(
        tracks=[track_out(t, settings, user_id) for t in hits["tracks"]],
        artists=[ArtistRef(id=a.id, name=a.name) for a in hits["artists"]],
        albums=[
            AlbumHit(id=a.id, title=a.title, artist=ArtistRef(id=a.artist.id, name=a.artist.name))
            for a in hits["albums"]
        ],
        playlists=[
            PlaylistHit(id=p.id, name=p.name, description=p.description, owner_id=p.owner_id)
            for p in hits["playlists"]
        ],
    )
