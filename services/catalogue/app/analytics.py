"""Per-user listening stats and recent-days history, read straight from `play_events`.

A "stream" only counts once a track has actually played for a while - a `play_end` with
`ms_played >= STREAM_THRESHOLD_MS` - not every tap on a row. Short accidental plays and
scrubbing around don't inflate anyone's "top track".
"""
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import Artist, PlayEvent, Track
from listens_common.web import current_user_id

from .schemas import ArtistRef, TrackOut
from .serialize import track_out

router = APIRouter()

STREAM_THRESHOLD_MS = 30_000


class TopTrackOut(BaseModel):
    track: TrackOut
    stream_count: int


class TopArtistOut(BaseModel):
    artist: ArtistRef
    play_count: int


class ListeningStatsOut(BaseModel):
    range: Literal["this_week", "last_week"]
    start: date
    end: date
    top_artist: TopArtistOut | None
    top_track: TopTrackOut | None


class RecentsDayOut(BaseModel):
    day: date
    play_count: int
    cover_track: TrackOut | None  # the day's most-played track, used as a representative cover


def _week_bounds(range_: str) -> tuple[date, date]:
    """Monday-Sunday, like most "this week / last week" UIs (including the one this mirrors)."""
    today = datetime.now(UTC).date()
    monday_this_week = today - timedelta(days=today.isoweekday() - 1)
    start = monday_this_week if range_ == "this_week" else monday_this_week - timedelta(days=7)
    return start, start + timedelta(days=6)


@router.get("/analytics/listening-stats", response_model=ListeningStatsOut)
def listening_stats(
    range: Literal["this_week", "last_week"] = Query("this_week"),
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> ListeningStatsOut:
    start, end = _week_bounds(range)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)  # exclusive

    artist_row = db.execute(
        select(Track.artist_id, func.count().label("n"))
        .join(PlayEvent, PlayEvent.track_id == Track.id)
        .where(
            PlayEvent.user_id == user_id, PlayEvent.event_type == "play_start",
            PlayEvent.occurred_at >= start_dt, PlayEvent.occurred_at < end_dt,
        )
        .group_by(Track.artist_id).order_by(func.count().desc()).limit(1)
    ).first()
    top_artist = None
    if artist_row and (artist := db.get(Artist, artist_row.artist_id)):
        top_artist = TopArtistOut(artist=ArtistRef(id=artist.id, name=artist.name), play_count=artist_row.n)

    track_row = db.execute(
        select(PlayEvent.track_id, func.count().label("n"))
        .where(
            PlayEvent.user_id == user_id, PlayEvent.event_type == "play_end", PlayEvent.ms_played >= STREAM_THRESHOLD_MS,
            PlayEvent.occurred_at >= start_dt, PlayEvent.occurred_at < end_dt,
        )
        .group_by(PlayEvent.track_id).order_by(func.count().desc()).limit(1)
    ).first()
    top_track = None
    if track_row and (t := db.get(Track, track_row.track_id)):
        top_track = TopTrackOut(track=track_out(t, settings, user_id), stream_count=track_row.n)

    return ListeningStatsOut(range=range, start=start, end=end, top_artist=top_artist, top_track=top_track)


@router.get("/analytics/recents", response_model=list[RecentsDayOut])
def recents(
    days: int = Query(14, ge=1, le=90), user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[RecentsDayOut]:
    """Per-day play counts, newest first, each day's "cover" being its most-played track that day."""
    day_expr = func.date(PlayEvent.occurred_at)
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(day_expr.label("day"), PlayEvent.track_id, func.count().label("n"))
        .where(PlayEvent.user_id == user_id, PlayEvent.event_type == "play_start", PlayEvent.occurred_at >= since)
        .group_by("day", PlayEvent.track_id)
    ).all()

    by_day: dict[date, dict[uuid.UUID, int]] = {}
    for day, track_id, n in rows:
        # Postgres' func.date() returns a date; SQLite's returns an ISO "YYYY-MM-DD" string.
        d = day if isinstance(day, date) else datetime.strptime(day, "%Y-%m-%d").date()
        by_day.setdefault(d, {})[track_id] = by_day.get(d, {}).get(track_id, 0) + n

    track_ids = {tid for counts in by_day.values() for tid in counts}
    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_(track_ids))).unique()}

    out = []
    for d, counts in sorted(by_day.items(), reverse=True):
        top_tid = max(counts, key=lambda tid: counts[tid])
        cover_track = tracks.get(top_tid)
        out.append(RecentsDayOut(
            day=d, play_count=sum(counts.values()),
            cover_track=track_out(cover_track, settings, user_id) if cover_track else None,
        ))
    return out
