import hashlib
import logging
import os
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from listens_common import albums as albumlib, artists, dedupe
from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import Album, Artist, Follow, Track, TrackArtist
from listens_common.storage import delete_prefix, get_s3
from listens_common.web import current_user_id, get_redis

from . import recommendations
from . import search as search_mod
from .analytics import router as analytics_router
from .events import router as events_router
from .library import router as library_router
from .schemas import (
    AlbumCardOut, AlbumDetail, AlbumHit, AlbumRef, ArtistDetail, ArtistRef, LyricsOut, PlaylistHit, SearchOut,
    TrackOut, UploadOut,
)
from .serialize import track_out
from .tags import read_duration_ms, read_lyrics, read_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("catalogue")

app = FastAPI(title="Shadow Listens - Catalogue", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(library_router)
app.include_router(events_router)
app.include_router(analytics_router)

TRANSCODE_STREAM = "jobs:transcode"
ALLOWED_EXT = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac"}
CHUNK = 1024 * 1024


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------- upload

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
    force: bool = Form(False),  # upload even if it looks like a song already in the library (a deliberate second version)
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
    lyrics = read_lyrics(file.file)
    stem = os.path.splitext(os.path.basename(file.filename or "Untitled"))[0]
    # Explicit form values win over embedded tags, which win over filename/"Unknown Artist".
    final_title = (title or tags.get("title") or stem).strip()[:200]
    final_artist = (artist or tags.get("artist") or "Unknown Artist").strip()[:200]
    album_name = album or tags.get("album")
    # Same song in a different file (e.g. a re-encode): refuse it the same way a byte-identical
    # upload is refused, before creating any artist/album rows or touching B2.
    # (checked before anything reaches B2). Exact and near matches alike: see dedupe.check_duplicate.
    duration_ms = read_duration_ms(file.file)
    match = None if force else dedupe.check_duplicate(
        db, user_id, title=final_title, credit=final_artist, album=album_name.strip() if album_name else None,
        duration_ms=duration_ms, sha256=digest,
    )
    if match:
        response.status_code = status.HTTP_200_OK
        return UploadOut(track=track_out(match.track, settings, user_id), duplicate=True, reason=match.reason)
    # one artist per person in the credit ("A/B", "A, B" and "A;B" all credit A and B); the first is the primary artist
    people = artists.ensure_artists(db, user_id, final_artist)
    artist_row = people[0]
    # the album title without store boilerplate; the same film under another first-listed singer is the same album
    album_row = albumlib.find_or_create_album(db, people, album_name.strip()) if album_name else None

    track_id = uuid.uuid4()
    source_key = f"originals/{track_id}/source{ext}"
    file.file.seek(0)
    s3 = get_s3()
    s3.upload_fileobj(file.file, settings.s3_bucket_audio, source_key)
    track = Track(
        id=track_id, artist_id=artist_row.id, album_id=album_row.id if album_row else None, uploader_id=user_id,
        title=final_title, genre=(genre or tags.get("genre") or None), license=license.strip(),
        status="uploaded", source_key=source_key, content_sha256=digest, duration_ms=duration_ms,
        lyrics=lyrics.get("lyrics"), lyrics_synced=lyrics.get("lyrics_synced"),
    )
    db.add(track)
    db.flush()
    artists.set_track_artists(db, track, people)
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


@app.get("/tracks/{track_id}/lyrics", response_model=LyricsOut)
def get_lyrics(
    track_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> LyricsOut:
    # Lyrics can be long, so they're fetched on demand (opening the lyrics panel), not
    # embedded in every TrackOut returned by list/search endpoints.
    track = _get_track(db, track_id)
    if track.status != "ready" and track.uploader_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return LyricsOut(lyrics=track.lyrics, lyrics_synced=track.lyrics_synced)


@app.get("/tracks/{track_id}/similar", response_model=list[TrackOut])
def get_similar_tracks(
    track_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    track = _get_track(db, track_id)
    if track.status != "ready" and track.uploader_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    picks = recommendations.similar_tracks(db, track, limit, user_id)
    return [track_out(t, settings, user_id) for t in picks]


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
    credited = select(TrackArtist.track_id).where(TrackArtist.artist_id == artist_id)
    # everything this artist is credited on, plus tracks not linked yet (the primary artist is always credited)
    tracks = db.scalars(
        _tracks_query().where(or_(Track.artist_id == artist_id, Track.id.in_(credited)), Track.status == "ready")
    ).unique()
    followed = db.get(Follow, (user_id, "artist", artist_id)) is not None
    return ArtistDetail(
        id=artist.id, name=artist.name, bio=artist.bio, followed=followed,
        tracks=[track_out(t, settings, user_id) for t in tracks],
    )


@app.get("/albums", response_model=list[AlbumCardOut])
def list_albums(
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AlbumCardOut]:
    """Every album that has at least one ready track, grouped from track metadata at upload
    time (see _find_or_create_album) - there's no separate "create an album" step; tagging a
    batch of uploads with the same album name (e.g. a movie soundtrack) is what creates one."""
    tracks = db.scalars(
        select(Track).where(Track.status == "ready", Track.album_id.is_not(None)).order_by(Track.created_at)
    ).unique().all()
    by_album: dict[uuid.UUID, list[Track]] = {}
    for t in tracks:
        by_album.setdefault(t.album_id, []).append(t)

    out = []
    for album_tracks in by_album.values():
        album = album_tracks[0].album
        cover_track = next((t for t in album_tracks if t.cover_key), album_tracks[0])
        out.append(AlbumCardOut(
            id=album.id, title=album.title, artist=ArtistRef(id=album.artist.id, name=album.artist.name),
            cover_url=track_out(cover_track, settings, user_id).cover_url,
            track_count=len(album_tracks),
        ))
    out.sort(key=lambda a: a.title.lower())
    return out


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

@app.get("/search/facets")
def search_facets(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> dict:
    """Genres and moods present in the library, for the search filter's quick picks."""
    return search_mod.facets(db)


@app.get("/search", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=50),
    by: str = Query("all", pattern="^(all|artist|album|genre|mood)$"),  # search one field instead of everything
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SearchOut:
    hits = search_mod.search(db, q.strip(), user_id, limit) if by == "all" else search_mod.search_by(db, q.strip(), by, limit)
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
