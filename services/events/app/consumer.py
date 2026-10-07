"""Redis Stream consumer: play/skip/like events -> the play_events table.

Same pattern as services/worker/app/jobs.py (consumer group, XACK+XDEL on success, XAUTOCLAIM
sweep for a crashed consumer's abandoned messages), trimmed down: there's no multi-stage
artifact to clean up on failure here, just a row to insert, so a failed insert is retried a
few times then the message is dropped (a lost analytics event is not worth blocking the stream
over - unlike a failed transcode, there's no user-visible "failed" state to show for it).
"""
import logging
import uuid
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy.orm import sessionmaker

from listens_common.models import PlayEvent

log = logging.getLogger("events")

STREAM = "jobs:events"
GROUP = "events-consumers"
CLAIM_IDLE_MS = 5 * 60 * 1000
BLOCK_MS = 5000
MAX_ATTEMPTS = 3

EVENT_TYPES = {"play_start", "play_end", "skip", "like", "add_to_playlist"}


def ensure_group(r: Redis) -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _to_int(fields: dict, key: str) -> int | None:
    v = fields.get(key)
    return int(v) if v not in (None, "") else None


def handle_message(r: Redis, sessions: sessionmaker, msg_id: str, fields: dict) -> None:
    attempt = int(fields.get("attempt", 0))
    try:
        event_type = fields["event_type"]
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {event_type!r}")
        row = PlayEvent(
            user_id=uuid.UUID(fields["user_id"]),
            track_id=uuid.UUID(fields["track_id"]),
            event_type=event_type,
            ms_played=_to_int(fields, "ms_played"),
            position_ms=_to_int(fields, "position_ms"),
            reason=fields.get("reason") or None,
            session_id=fields.get("session_id") or None,
            occurred_at=datetime.fromisoformat(fields["occurred_at"]),
        )
        with sessions() as db:
            db.add(row)
            db.commit()
    except Exception:  # noqa: BLE001 - malformed message or a transient DB error either way
        log.exception("failed to process event %s (attempt %d): %r", msg_id, attempt + 1, fields)
        if attempt + 1 < MAX_ATTEMPTS:
            r.xadd(STREAM, {**fields, "attempt": str(attempt + 1)})
        else:
            log.error("dropping event %s after %d attempts: %r", msg_id, MAX_ATTEMPTS, fields)
    r.xack(STREAM, GROUP, msg_id)
    r.xdel(STREAM, msg_id)


def poll_once(r: Redis, sessions: sessionmaker, consumer: str, block_ms: int = BLOCK_MS) -> int:
    try:
        resp = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=10, block=block_ms)
    except ResponseError as exc:
        if "NOGROUP" not in str(exc) and "requires the key to exist" not in str(exc):
            raise
        ensure_group(r)
        return 0
    handled = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            handle_message(r, sessions, msg_id, fields)
            handled += 1
    return handled


def sweep(r: Redis, sessions: sessionmaker, consumer: str) -> None:
    _, claimed, *_ = r.xautoclaim(STREAM, GROUP, consumer, min_idle_time=CLAIM_IDLE_MS, count=50)
    for msg_id, fields in claimed:
        handle_message(r, sessions, msg_id, fields)


def run_forever(r: Redis, sessions: sessionmaker, consumer: str) -> None:
    import time

    ensure_group(r)
    last_sweep = 0.0
    while True:
        try:
            if time.monotonic() - last_sweep > 60:
                last_sweep = time.monotonic()
                sweep(r, sessions, consumer)
            poll_once(r, sessions, consumer)
        except (RedisError, OSError):
            log.exception("redis error; retrying in 3s")
            time.sleep(3)
        except Exception:  # noqa: BLE001
            log.exception("unexpected error in events consumer loop; continuing")
            time.sleep(1)
