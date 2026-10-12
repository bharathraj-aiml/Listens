"""Client event ingestion: play_start / play_end / skip -> the `play_events` table.

Each event is inserted directly, so "Recently played" and the recommender see a play the moment it
happens. If that insert fails (database asleep or briefly unreachable) the event falls back to the
Redis Stream `jobs:events`, which the `events` service (services/events/) drains into the same table,
so a hiccup never loses an event. With EVENTS_VIA_QUEUE=true every event goes to the stream, the
original design for a stack that runs the always-on consumer (docker-compose).

`like` and `add_to_playlist` events are emitted as a side effect of the existing /likes and
/playlists/*/tracks endpoints (see library.py), not accepted here - that keeps one source of
truth for the actual mutation instead of asking the client to make two calls for one action.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import PlayEvent
from listens_common.web import current_user_id, get_redis

router = APIRouter()
log = logging.getLogger("catalogue")

STREAM = "jobs:events"


class ClientEventIn(BaseModel):
    event_type: Literal["play_start", "play_end", "skip"]
    track_id: uuid.UUID
    ms_played: int | None = Field(default=None, ge=0)
    position_ms: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=40)
    session_id: str | None = Field(default=None, max_length=64)


def publish_event(
    r: Redis, *, event_type: str, user_id: uuid.UUID, track_id: uuid.UUID,
    ms_played: int | None = None, position_ms: int | None = None,
    reason: str | None = None, session_id: str | None = None,
) -> None:
    fields = {
        "event_type": event_type, "user_id": str(user_id), "track_id": str(track_id),
        "occurred_at": datetime.now(UTC).isoformat(), "attempt": "0",
    }
    if ms_played is not None:
        fields["ms_played"] = str(ms_played)
    if position_ms is not None:
        fields["position_ms"] = str(position_ms)
    if reason:
        fields["reason"] = reason
    if session_id:
        fields["session_id"] = session_id
    r.xadd(STREAM, fields)


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
def record_event(
    body: ClientEventIn, user_id: uuid.UUID = Depends(current_user_id), r: Redis = Depends(get_redis),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> None:
    if not settings.events_via_queue:
        try:
            db.add(PlayEvent(
                user_id=user_id, track_id=body.track_id, event_type=body.event_type, ms_played=body.ms_played,
                position_ms=body.position_ms, reason=body.reason, session_id=body.session_id, occurred_at=datetime.now(UTC),
            ))
            db.commit()
            return
        except Exception:  # noqa: BLE001 - never lose the event: hand it to the queue instead
            db.rollback()
            log.exception("direct play-event insert failed; falling back to the queue")
    publish_event(
        r, event_type=body.event_type, user_id=user_id, track_id=body.track_id,
        ms_played=body.ms_played, position_ms=body.position_ms, reason=body.reason, session_id=body.session_id,
    )
