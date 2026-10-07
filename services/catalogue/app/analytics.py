"""Simple, per-user listening analytics, read straight from `play_events`.

A "stream" only counts once a track has actually played for a while - a `play_end` with
`ms_played >= STREAM_THRESHOLD_MS` - not every tap on a row. Short accidental plays and
scrubbing around don't inflate anyone's "top tracks".
"""
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import PlayEvent, Track
from listens_common.web import current_user_id

from .schemas import TrackOut
from .serialize import track_out

router = APIRouter()

STREAM_THRESHOLD_MS = 30_000
MIN_PLAYS_FOR_SKIP_RATE = 2  # one play + one skip would otherwise show as a meaningless 100%


class TopTrackOut(BaseModel):
    track: TrackOut
    stream_count: int


class SkipRateOut(BaseModel):
    track: TrackOut
    play_count: int
    skip_count: int
    skip_rate: float  # 0..1


class HourBucket(BaseModel):
    hour: int  # 0-23, UTC
    count: int


@router.get("/analytics/top-tracks", response_model=list[TopTrackOut])
def top_tracks(
    limit: int = Query(20, ge=1, le=100), user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[TopTrackOut]:
    rows = db.execute(
        select(PlayEvent.track_id, func.count().label("n"))
        .where(PlayEvent.user_id == user_id, PlayEvent.event_type == "play_end", PlayEvent.ms_played >= STREAM_THRESHOLD_MS)
        .group_by(PlayEvent.track_id).order_by(func.count().desc()).limit(limit)
    ).all()
    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_([r.track_id for r in rows]))).unique()}
    return [
        TopTrackOut(track=track_out(tracks[r.track_id], settings, user_id), stream_count=r.n)
        for r in rows if r.track_id in tracks
    ]


@router.get("/analytics/skip-rate", response_model=list[SkipRateOut])
def skip_rate(
    limit: int = Query(20, ge=1, le=100), user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[SkipRateOut]:
    plays = dict(db.execute(
        select(PlayEvent.track_id, func.count()).where(PlayEvent.user_id == user_id, PlayEvent.event_type == "play_start")
        .group_by(PlayEvent.track_id)
    ).all())
    skips = dict(db.execute(
        select(PlayEvent.track_id, func.count()).where(PlayEvent.user_id == user_id, PlayEvent.event_type == "skip")
        .group_by(PlayEvent.track_id)
    ).all())
    eligible = [tid for tid, n in plays.items() if n >= MIN_PLAYS_FOR_SKIP_RATE]
    eligible.sort(key=lambda tid: skips.get(tid, 0) / plays[tid], reverse=True)
    eligible = eligible[:limit]

    tracks = {t.id: t for t in db.scalars(select(Track).where(Track.id.in_(eligible))).unique()}
    out = []
    for tid in eligible:
        t = tracks.get(tid)
        if not t:
            continue
        play_count, skip_count = plays[tid], skips.get(tid, 0)
        out.append(SkipRateOut(
            track=track_out(t, settings, user_id), play_count=play_count, skip_count=skip_count,
            skip_rate=round(skip_count / play_count, 4),
        ))
    return out


@router.get("/analytics/listening-by-hour", response_model=list[HourBucket])
def listening_by_hour(user_id: uuid.UUID = Depends(current_user_id), db: Session = Depends(get_db)) -> list[HourBucket]:
    hour = func.extract("hour", PlayEvent.occurred_at)
    rows = db.execute(
        select(hour.label("hour"), func.count())
        .where(PlayEvent.user_id == user_id, PlayEvent.event_type == "play_start")
        .group_by(hour)
    ).all()
    counts = {int(h): n for h, n in rows}
    return [HourBucket(hour=h, count=counts.get(h, 0)) for h in range(24)]
