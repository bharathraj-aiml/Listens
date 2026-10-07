"""Client event ingestion: play_start / play_end / skip -> Redis Stream `jobs:events`.

A dedicated `events` service consumes that stream and writes rows into `play_events` (see
services/events/). Publishing here is fire-and-forget: the HTTP call returns as soon as the
XADD is acknowledged by Redis, not once the row exists in Postgres - this endpoint is on the
hot path (every skip, every track change) and shouldn't block on a database round trip.

`like` and `add_to_playlist` events are emitted as a side effect of the existing /likes and
/playlists/*/tracks endpoints (see library.py), not accepted here - that keeps one source of
truth for the actual mutation instead of asking the client to make two calls for one action.
"""
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from redis import Redis

from listens_common.web import current_user_id, get_redis

router = APIRouter()

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
) -> None:
    publish_event(
        r, event_type=body.event_type, user_id=user_id, track_id=body.track_id,
        ms_played=body.ms_played, position_ms=body.position_ms, reason=body.reason, session_id=body.session_id,
    )
