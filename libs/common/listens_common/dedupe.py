"""Duplicate-song detection, shared by the upload endpoint (reject), the transcode worker (delete the
lower-quality copy once a track is ready) and scripts/dedupe_library.py (one-off cleanup of the library).

Byte-identical files are already stopped by the (uploader, sha256) unique index. This covers the same
SONG in a different file, e.g. a re-encode: same uploader, same normalised title + artist, compatible
album, and (once both are transcoded) lengths within a few seconds.
"""
import unicodedata
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import Album, Artist, Like, PlaylistTrack, Track

DURATION_TOLERANCE_MS = 3000
LIVE_STATUSES = ("uploaded", "processing", "ready")
# Untagged files fall back to a filename title + this artist, so a match proves nothing.
UNKNOWN_ARTISTS = {"", "unknown artist"}


def norm(text: str | None) -> str:
    """Case/punctuation/spacing-insensitive key. Keeps letters, marks and digits of every script
    (marks matter: dropping Tamil vowel signs would make different words collide)."""
    s = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join("".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in s).split())


def _album_compatible(a: str | None, b: str | None) -> bool:
    na, nb = norm(a), norm(b)
    return not na or not nb or na == nb  # a missing album doesn't make it a different song


def find_duplicates(
    db: Session, uploader_id: uuid.UUID | None, title: str, artist: str, album: str | None = None,
    *, duration_ms: int | None = None, exclude_id: uuid.UUID | None = None,
) -> list[Track]:
    """Existing (not failed) tracks of this uploader that are the same song. With duration_ms given,
    a candidate must also have a known duration within DURATION_TOLERANCE_MS."""
    if uploader_id is None or norm(artist) in UNKNOWN_ARTISTS or not norm(title):
        return []
    nt, na = norm(title), norm(artist)
    rows = db.execute(
        select(Track, Artist.name, Album.title)
        .join(Artist, Artist.id == Track.artist_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(Track.uploader_id == uploader_id, Track.status.in_(LIVE_STATUSES))
    ).all()
    out = []
    for t, artist_name, album_title in rows:
        if t.id == exclude_id or norm(t.title) != nt or norm(artist_name) != na:
            continue
        if not _album_compatible(album, album_title):
            continue
        if duration_ms is not None and (t.duration_ms is None or abs(t.duration_ms - duration_ms) > DURATION_TOLERANCE_MS):
            continue
        out.append(t)
    return out


def pick_keeper(tracks: list[Track]) -> Track:
    """Highest source bitrate wins; on a tie the oldest upload (it's the one already in playlists)."""
    return min(tracks, key=lambda t: (-(t.source_bitrate_kbps or 0), t.created_at, str(t.id)))


def remove_track(db: Session, s3, settings, track: Track, keep: Track | None = None) -> None:
    """Delete a track's rows and its B2 files. Likes and playlist entries move to `keep` first."""
    from .storage import delete_prefix  # lazy: only services with the [storage] extra need boto3

    tid, cover_key = track.id, track.cover_key
    if keep is not None:
        for like in db.scalars(select(Like).where(Like.track_id == tid)).all():
            if db.get(Like, (like.user_id, keep.id)) is None:
                db.add(Like(user_id=like.user_id, track_id=keep.id, created_at=like.created_at))
        db.execute(update(PlaylistTrack).where(PlaylistTrack.track_id == tid).values(track_id=keep.id))
    db.execute(delete(Like).where(Like.track_id == tid))
    db.delete(track)
    db.commit()
    delete_prefix(s3, settings.s3_bucket_audio, f"originals/{tid}/")
    delete_prefix(s3, settings.s3_bucket_audio, f"hls/{tid}/")
    if cover_key:
        s3.delete_object(Bucket=settings.s3_bucket_covers, Key=cover_key)


def duplicate_group(db: Session, track: Track) -> list[Track]:
    """`track` plus every other READY copy of the same song (empty list entries excluded)."""
    artist = db.get(Artist, track.artist_id)
    album = db.get(Album, track.album_id) if track.album_id else None
    twins = find_duplicates(db, track.uploader_id, track.title, artist.name if artist else "",
                            album.title if album else None, duration_ms=track.duration_ms, exclude_id=track.id)
    twins = [t for t in twins if t.status == "ready"]
    return [track, *twins] if twins else []


def resolve_duplicates(db: Session, s3, settings, track_id: uuid.UUID) -> list[uuid.UUID]:
    """Called when a track becomes ready: keep the best copy of the song, delete the rest.
    Returns the ids that were removed (possibly including `track_id` itself)."""
    track = db.get(Track, track_id)
    if track is None or track.status != "ready":
        return []
    group = duplicate_group(db, track)
    if not group:
        return []
    keeper = pick_keeper(group)
    removed = []
    for t in group:
        if t.id != keeper.id:
            removed.append(t.id)
            remove_track(db, s3, settings, t, keep=keeper)
    return removed
