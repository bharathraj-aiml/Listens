"""Transcode job pipeline: Redis Stream + consumer group, at-least-once delivery.

Track state machine:   uploaded --claim--> processing --> ready
                                              |--> (retry) uploaded, up to MAX_ATTEMPTS, then failed

Why a Stream instead of a list: XREADGROUP + XACK means a job is only removed once handled, and
XAUTOCLAIM lets a healthy worker take over jobs from one that crashed mid-transcode.
Handling is idempotent (the atomic claim below), so a duplicate delivery is harmless.
"""
import logging
import tempfile
import uuid
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from redis import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from listens_common.config import Settings
from listens_common.models import Track
from listens_common.storage import delete_prefix

from . import transcode

log = logging.getLogger("worker")

STREAM = "jobs:transcode"
GROUP = "transcoders"
MAX_ATTEMPTS = 3
CLAIM_IDLE_MS = 10 * 60 * 1000  # a job unacked this long belongs to a dead worker
STUCK_UPLOADED = timedelta(minutes=2)  # grace period before we suspect a lost enqueue
STUCK_PROCESSING = timedelta(minutes=45)  # worker died mid-run


def ensure_group(r: Redis) -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def process_track(db: Session, s3, settings: Settings, track_id) -> str:
    """Transcode one track. Returns 'ready' | 'skipped'. Raises on failure (caller handles retry)."""
    # Atomic claim: only one worker can flip uploaded -> processing.
    claimed = db.execute(
        update(Track).where(Track.id == track_id, Track.status == "uploaded")
        .values(status="processing", processing_started_at=datetime.now(UTC))
    ).rowcount
    db.commit()
    if not claimed:
        return "skipped"  # already processing/ready/failed, or the track was deleted

    track = db.get(Track, track_id)
    with tempfile.TemporaryDirectory(prefix="transcode-") as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / "source"
        s3.download_file(settings.s3_bucket_audio, track.source_key, str(src))

        info = transcode.probe(src)
        renditions = transcode.select_renditions(info.bitrate_kbps)
        out = tmp_dir / "hls"
        transcode.transcode_hls(src, out, renditions, settings.hls_audio_codec)

        prefix = f"hls/{track_id}"
        delete_prefix(s3, settings.s3_bucket_audio, prefix + "/")  # clean leftovers from a prior attempt
        for f in sorted(out.rglob("*")):
            if f.is_file():
                ctype = "application/vnd.apple.mpegurl" if f.suffix == ".m3u8" else "video/mp2t"
                s3.upload_file(str(f), settings.s3_bucket_audio, f"{prefix}/{f.relative_to(out).as_posix()}",
                               ExtraArgs={"ContentType": ctype})

        cover_key = None
        cover = tmp_dir / "cover.jpg"
        if transcode.extract_cover(src, cover):
            cover_key = f"tracks/{track_id}.jpg"
            s3.upload_file(str(cover), settings.s3_bucket_covers, cover_key, ExtraArgs={"ContentType": "image/jpeg"})

    db.execute(
        update(Track).where(Track.id == track_id).values(
            status="ready", hls_prefix=prefix, duration_ms=info.duration_ms,
            source_bitrate_kbps=info.bitrate_kbps, cover_key=cover_key, error=None,
        )
    )
    db.commit()
    log.info("track %s ready (%d ms, %s kbps, %d renditions)", track_id, info.duration_ms, info.bitrate_kbps, len(renditions))
    return "ready"


def handle_message(r: Redis, sessions: sessionmaker, s3, settings: Settings, msg_id: str, fields: dict) -> None:
    try:
        track_id, attempt = uuid.UUID(fields["track_id"]), int(fields.get("attempt", 0))
    except (KeyError, ValueError):
        log.error("dropping malformed job %s: %r", msg_id, fields)  # poison message: never retry
        r.xack(STREAM, GROUP, msg_id)
        r.xdel(STREAM, msg_id)
        return
    with sessions() as db:
        try:
            process_track(db, s3, settings, track_id)
        except Exception as exc:  # noqa: BLE001 - any failure must end in retry or 'failed'
            db.rollback()
            log.exception("track %s failed (attempt %d)", track_id, attempt + 1)
            if attempt + 1 < MAX_ATTEMPTS:
                db.execute(update(Track).where(Track.id == track_id, Track.status == "processing").values(status="uploaded"))
                db.commit()
                r.xadd(STREAM, {"track_id": str(track_id), "attempt": str(attempt + 1)})
            else:
                db.execute(
                    update(Track).where(Track.id == track_id).values(status="failed", error=str(exc)[:1000])
                )
                db.commit()
    r.xack(STREAM, GROUP, msg_id)
    r.xdel(STREAM, msg_id)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive datetimes


def requeue_stuck(r: Redis, sessions: sessionmaker) -> int:
    """Safety net: reset hung 'processing' tracks, and re-enqueue 'uploaded' tracks whose job
    is missing from the stream (lost enqueue). Tracks merely waiting in the queue are left alone."""
    now = datetime.now(UTC)
    n = 0
    queued = {fields["track_id"] for _, fields in r.xrange(STREAM)}
    with sessions() as db:
        for t in db.scalars(select(Track).where(Track.status == "processing")):
            if t.processing_started_at is None or now - _aware(t.processing_started_at) > STUCK_PROCESSING:
                t.status = "uploaded"
        db.commit()
        for t in db.scalars(select(Track).where(Track.status == "uploaded")):
            if str(t.id) not in queued and now - _aware(t.created_at) > STUCK_UPLOADED:
                r.xadd(STREAM, {"track_id": str(t.id), "attempt": "0"})
                n += 1
    return n


BLOCK_MS = 5000


def poll_once(r: Redis, sessions: sessionmaker, s3, settings: Settings, consumer: str, block_ms: int = BLOCK_MS) -> int:
    """Read and handle at most one job (blocking up to block_ms). Returns the number handled."""
    try:
        resp = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=block_ms)
    except ResponseError as exc:
        # Real Redis says "NOGROUP ..."; fakeredis words the same condition differently.
        if "NOGROUP" not in str(exc) and "requires the key to exist" not in str(exc):
            raise
        ensure_group(r)  # Redis restarted/flushed without our group: recreate it and carry on
        return 0
    handled = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            handle_message(r, sessions, s3, settings, msg_id, fields)
            handled += 1
    return handled


def sweep(r: Redis, sessions: sessionmaker, s3, settings: Settings, consumer: str) -> None:
    # take over jobs a crashed worker never acked, then re-enqueue lost ones
    _, claimed, *_ = r.xautoclaim(STREAM, GROUP, consumer, min_idle_time=CLAIM_IDLE_MS, count=10)
    for msg_id, fields in claimed:
        handle_message(r, sessions, s3, settings, msg_id, fields)
    if (n := requeue_stuck(r, sessions)):
        log.info("sweep re-enqueued %d stuck tracks", n)


def run_forever(r: Redis, sessions: sessionmaker, s3, settings: Settings, consumer: str) -> None:
    ensure_group(r)
    last_sweep = 0.0
    while True:
        try:
            if time.monotonic() - last_sweep > 60:
                last_sweep = time.monotonic()
                sweep(r, sessions, s3, settings, consumer)
            poll_once(r, sessions, s3, settings, consumer)
        except (RedisError, OSError):
            # Redis unreachable or restarting: back off and retry instead of dying.
            log.exception("redis error; retrying in 3s")
            time.sleep(3)
        except Exception:  # noqa: BLE001 - never let one bad iteration kill the worker
            log.exception("unexpected error in worker loop; continuing")
            time.sleep(1)
