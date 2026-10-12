"""Playlists, likes, follows, play history, and the Home page's personalised sections.

Permission model (kept deliberately simple - this is a personal/household server, not a
multi-tenant product): a playlist is visible to everyone if `is_public`, otherwise only to
its owner. Any authenticated user can add/remove/reorder tracks on a playlist that is
`is_collaborative` (there's no per-playlist member list - "collaborative" means "anyone
with an account on this server can edit it"). Only the owner can rename, delete, or change
a playlist's visibility/collaborative flag.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis import Redis
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import Artist, Follow, Like, PlayEvent, Playlist, PlaylistTrack, Track, User
from listens_common.web import current_user_id, get_redis

from . import recommendations
from .events import publish_event
from .schemas import (
    AddTrackIn, ArtistRef, PlaylistCreateIn, PlaylistDetailOut, PlaylistOut,
    PlaylistTrackOut, PlaylistUpdateIn, ReorderIn, TrackOut, UserRef,
)
from .serialize import track_out

router = APIRouter()


# ---------------------------------------------------------------- playlists

def _cover_url_for(db: Session, playlist_id: uuid.UUID, settings: Settings, user_id: uuid.UUID) -> str | None:
    first = db.scalar(
        select(Track).join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist_id, Track.cover_key.is_not(None))
        .order_by(PlaylistTrack.position).limit(1)
    )
    return track_out(first, settings, user_id).cover_url if first else None


def _playlist_out(db: Session, p: Playlist, settings: Settings, user_id: uuid.UUID) -> PlaylistOut:
    count = db.scalar(select(func.count()).select_from(PlaylistTrack).where(PlaylistTrack.playlist_id == p.id)) or 0
    return PlaylistOut(
        id=p.id, name=p.name, description=p.description, owner_id=p.owner_id,
        is_public=p.is_public, is_collaborative=p.is_collaborative, track_count=count,
        cover_url=_cover_url_for(db, p.id, settings, user_id), created_at=p.created_at, updated_at=p.updated_at,
    )


def _get_visible_playlist(db: Session, playlist_id: uuid.UUID, user_id: uuid.UUID) -> Playlist:
    p = db.get(Playlist, playlist_id)
    if p is None or (not p.is_public and p.owner_id != user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    return p


def _get_editable_playlist(db: Session, playlist_id: uuid.UUID, user_id: uuid.UUID) -> Playlist:
    p = _get_visible_playlist(db, playlist_id, user_id)
    if p.owner_id != user_id and not p.is_collaborative:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can edit this playlist")
    return p


@router.post("/playlists", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
def create_playlist(
    body: PlaylistCreateIn, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> PlaylistOut:
    p = Playlist(owner_id=user_id, name=body.name.strip(), description=body.description,
                is_public=body.is_public, is_collaborative=body.is_collaborative)
    db.add(p)
    db.commit()
    return _playlist_out(db, p, settings, user_id)


@router.get("/playlists/mine", response_model=list[PlaylistOut])
def list_my_playlists(
    user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[PlaylistOut]:
    rows = db.scalars(select(Playlist).where(Playlist.owner_id == user_id).order_by(Playlist.updated_at.desc()))
    return [_playlist_out(db, p, settings, user_id) for p in rows]


@router.get("/playlists/{playlist_id}", response_model=PlaylistDetailOut)
def get_playlist(
    playlist_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> PlaylistDetailOut:
    p = _get_visible_playlist(db, playlist_id, user_id)
    rows = db.scalars(
        select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id).order_by(PlaylistTrack.position, PlaylistTrack.id)
    ).unique()
    base = _playlist_out(db, p, settings, user_id)
    tracks = [
        PlaylistTrackOut(id=pt.id, position=pt.position, added_by=pt.added_by, added_at=pt.added_at,
                         track=track_out(pt.track, settings, user_id))
        for pt in rows
    ]
    return PlaylistDetailOut(**base.model_dump(), tracks=tracks)


@router.patch("/playlists/{playlist_id}", response_model=PlaylistOut)
def update_playlist(
    playlist_id: uuid.UUID, body: PlaylistUpdateIn, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> PlaylistOut:
    p = db.get(Playlist, playlist_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    if p.owner_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can change playlist settings")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(p, field, value)
    db.add(p)
    db.commit()
    return _playlist_out(db, p, settings, user_id)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(playlist_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    p = db.get(Playlist, playlist_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    if p.owner_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete this playlist")
    db.delete(p)
    db.commit()


@router.post("/playlists/{playlist_id}/tracks", response_model=PlaylistTrackOut, status_code=status.HTTP_201_CREATED)
def add_track(
    playlist_id: uuid.UUID, body: AddTrackIn, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings), r: Redis = Depends(get_redis),
) -> PlaylistTrackOut:
    p = _get_editable_playlist(db, playlist_id, user_id)
    track = db.get(Track, body.track_id)
    if track is None or track.status != "ready":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    # NOT `... or -1`: that treats position 0 (the first track) as falsy and duplicates it.
    max_pos = db.scalar(select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id))
    next_pos = 0 if max_pos is None else max_pos + 1
    pt = PlaylistTrack(playlist_id=p.id, track_id=track.id, position=next_pos, added_by=user_id)
    db.add(pt)
    p.updated_at = datetime.now(UTC)
    db.add(p)
    db.commit()
    db.refresh(pt)
    publish_event(r, event_type="add_to_playlist", user_id=user_id, track_id=track.id)
    return PlaylistTrackOut(id=pt.id, position=pt.position, added_by=pt.added_by, added_at=pt.added_at,
                            track=track_out(track, settings, user_id))


@router.delete("/playlists/{playlist_id}/tracks/{playlist_track_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_track(
    playlist_id: uuid.UUID, playlist_track_id: int, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db),
) -> None:
    p = _get_editable_playlist(db, playlist_id, user_id)
    pt = db.get(PlaylistTrack, playlist_track_id)
    if pt is None or pt.playlist_id != p.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not in this playlist")
    db.delete(pt)
    p.updated_at = datetime.now(UTC)
    db.add(p)
    db.commit()


@router.post("/playlists/{playlist_id}/tracks/{playlist_track_id}/move", response_model=list[PlaylistTrackOut])
def move_track(
    playlist_id: uuid.UUID, playlist_track_id: int, body: ReorderIn, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[PlaylistTrackOut]:
    """Move one track to `to_index` (0-based) and renumber the rest. Simple full-renumber
    approach - fine at personal-playlist sizes, not optimised for huge playlists."""
    p = _get_editable_playlist(db, playlist_id, user_id)
    rows = list(db.scalars(
        select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id).order_by(PlaylistTrack.position, PlaylistTrack.id)
    ))
    moving = next((r for r in rows if r.id == playlist_track_id), None)
    if moving is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not in this playlist")
    rows.remove(moving)
    target = max(0, min(body.to_index, len(rows)))
    rows.insert(target, moving)
    for i, r in enumerate(rows):
        r.position = i
    p.updated_at = datetime.now(UTC)
    db.add(p)
    db.commit()
    return [
        PlaylistTrackOut(id=r.id, position=r.position, added_by=r.added_by, added_at=r.added_at,
                         track=track_out(r.track, settings, user_id))
        for r in rows
    ]


# ---------------------------------------------------------------- likes

@router.post("/likes/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def like_track(
    track_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), r: Redis = Depends(get_redis),
) -> None:
    track = db.get(Track, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    if db.get(Like, (user_id, track_id)) is None:  # idempotent: liking twice is a no-op, not a conflict
        db.add(Like(user_id=user_id, track_id=track_id))
        db.commit()
        publish_event(r, event_type="like", user_id=user_id, track_id=track_id)


@router.delete("/likes/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlike_track(track_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    db.execute(sa_delete(Like).where(Like.user_id == user_id, Like.track_id == track_id))
    db.commit()


@router.get("/likes", response_model=list[TrackOut])
def list_likes(
    user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    rows = db.scalars(
        select(Track).join(Like, Like.track_id == Track.id)
        .where(Like.user_id == user_id, Track.status == "ready").order_by(Like.created_at.desc())
    ).unique()
    return [track_out(t, settings, user_id) for t in rows]


@router.get("/likes/ids", response_model=list[uuid.UUID])
def list_like_ids(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> list[uuid.UUID]:
    """Cheap set of liked track ids, for the UI to highlight hearts without an N+1 per row."""
    return list(db.scalars(select(Like.track_id).where(Like.user_id == user_id)))


# ---------------------------------------------------------------- follows

@router.post("/follows/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def follow_artist(artist_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    if db.get(Artist, artist_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    if db.get(Follow, (user_id, "artist", artist_id)) is None:
        db.add(Follow(follower_id=user_id, target_type="artist", target_id=artist_id))
        db.commit()


@router.delete("/follows/artists/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_artist(artist_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    db.execute(sa_delete(Follow).where(Follow.follower_id == user_id, Follow.target_type == "artist", Follow.target_id == artist_id))
    db.commit()


@router.get("/follows/artists", response_model=list[ArtistRef])
def list_followed_artists(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> list[ArtistRef]:
    rows = db.scalars(
        select(Artist).join(Follow, Follow.target_id == Artist.id)
        .where(Follow.follower_id == user_id, Follow.target_type == "artist").order_by(Artist.name)
    )
    return [ArtistRef(id=a.id, name=a.name) for a in rows]


@router.post("/follows/users/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def follow_user(target_user_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    if target_user_id == user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't follow yourself")
    if db.get(User, target_user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if db.get(Follow, (user_id, "user", target_user_id)) is None:
        db.add(Follow(follower_id=user_id, target_type="user", target_id=target_user_id))
        db.commit()


@router.delete("/follows/users/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_user(target_user_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> None:
    db.execute(sa_delete(Follow).where(Follow.follower_id == user_id, Follow.target_type == "user", Follow.target_id == target_user_id))
    db.commit()


@router.get("/follows/users", response_model=list[UserRef])
def list_followed_users(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> list[UserRef]:
    rows = db.scalars(
        select(User).join(Follow, Follow.target_id == User.id)
        .where(Follow.follower_id == user_id, Follow.target_type == "user").order_by(User.username)
    )
    return [UserRef(id=u.id, username=u.username, display_name=u.display_name) for u in rows]


# ---------------------------------------------------------------- home sections
# Play events (play_start/play_end/skip) now arrive via POST /events -> Redis Stream -> the
# events service, not a direct write here (see events.py). These read queries are unchanged.

QUICK_SKIP_MS = 8_000  # a song dropped before this was a tap-through, not something you listened to


def last_listens(db: Session, user_id: uuid.UUID, limit: int) -> list[tuple[uuid.UUID, datetime]]:
    """(track id, when you last listened) newest first, for songs you actually listened to.

    A play_start counts unless the same song was skipped within QUICK_SKIP_MS of it. Tapping through a
    queue to find something therefore does not fill "Recently played" with songs you never heard. A start
    with no matching end (the song playing right now) counts. Done in Python over the newest events so it
    behaves identically on Postgres and SQLite."""
    rows = db.execute(
        select(PlayEvent.track_id, PlayEvent.event_type, PlayEvent.occurred_at, PlayEvent.position_ms)
        .where(PlayEvent.user_id == user_id, PlayEvent.event_type.in_(("play_start", "play_end", "skip")))
        .order_by(PlayEvent.occurred_at.desc()).limit(max(limit * 40, 400))
    ).all()
    best: dict[uuid.UUID, datetime] = {}
    pending: dict[uuid.UUID, datetime | None] = {}
    for track_id, kind, at, position in reversed(rows):  # oldest first
        if kind == "play_start":
            if pending.get(track_id) is not None:  # the previous start never got an end event: it still counts
                best[track_id] = max(best.get(track_id, pending[track_id]), pending[track_id])
            pending[track_id] = at
        elif pending.get(track_id) is not None:
            if kind == "skip" and position is not None and position < QUICK_SKIP_MS:
                pending[track_id] = None  # dropped within seconds: not a listen
            else:
                best[track_id] = max(best.get(track_id, pending[track_id]), pending[track_id])
                pending[track_id] = None
    for track_id, at in pending.items():  # still playing, or never ended
        if at is not None:
            best[track_id] = max(best.get(track_id, at), at)
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:limit]


@router.get("/home/recently-played", response_model=list[TrackOut])
def recently_played(
    limit: int = Query(20, ge=1, le=50), user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    listens = last_listens(db, user_id, limit * 2)  # headroom: some songs may since have been deleted
    if not listens:
        return []
    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_([t for t, _ in listens]), Track.status == "ready")).unique()}
    out = []
    for track_id, at in listens:
        if track_id in tracks:
            item = track_out(tracks[track_id], settings, user_id)
            item.played_at = at
            out.append(item)
    return out[:limit]


@router.get("/home/made-for-you", response_model=list[TrackOut])
def made_for_you(
    limit: int = Query(20, ge=1, le=50), user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[TrackOut]:
    """Scores tracks by the nightly ALS model (services/recommender) once a user has a trained
    vector. Until then - or if ALS still can't fill the full page (a very sparse profile) -
    falls back to a heuristic: tracks by artists you've liked or played, that you haven't
    already played, then newest-ready tracks, so new users never see an empty section."""
    picks = recommendations.hybrid_made_for_you(db, user_id, limit)
    if picks is None:  # nothing to compare on yet: the ALS / heuristic path below
        picks = list(recommendations.als_made_for_you(db, user_id, limit) or [])
    played_tracks = select(PlayEvent.track_id).where(PlayEvent.user_id == user_id)

    if len(picks) < limit:
        have = {t.id for t in picks}
        liked_artists = select(Track.artist_id).join(Like, Like.track_id == Track.id).where(Like.user_id == user_id)
        played_artists = select(Track.artist_id).join(PlayEvent, PlayEvent.track_id == Track.id).where(PlayEvent.user_id == user_id)
        heuristic = db.scalars(
            select(Track).where(
                Track.status == "ready",
                Track.artist_id.in_(liked_artists.union(played_artists)),
                Track.id.not_in(played_tracks),
                Track.id.not_in(have),
            ).order_by(func.random()).limit(limit - len(picks))
        ).unique()
        picks += [t for t in heuristic if t.id not in have]

    if len(picks) < limit:
        have = {t.id for t in picks}
        fallback = db.scalars(
            select(Track).where(Track.status == "ready", Track.id.not_in(have), Track.id.not_in(played_tracks))
            .order_by(Track.created_at.desc()).limit(limit - len(picks))
        ).unique()
        picks += [t for t in fallback if t.id not in have]

    # Re-apply the cap: the heuristic/new-release fill-in above doesn't know about it, so
    # without this a thin ALS result could get "topped up" past 2-per-artist by either of them.
    picks = recommendations.cap_per_artist(picks)
    return [track_out(t, settings, user_id) for t in picks]
