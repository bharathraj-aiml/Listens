from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app import jobs
from listens_common import testing
from listens_common.models import Track


def keys(env, bucket=None, prefix=""):
    resp = env.s3.list_objects_v2(Bucket=bucket or env.cfg.s3_bucket_audio, Prefix=prefix)
    return sorted(o["Key"] for o in resp.get("Contents", []))


def test_process_track_end_to_end(env):
    src = testing.make_audio(env.dir / "s.mp3", seconds=8, cover=True, bitrate="192k")
    tid = env.add_track(src)
    with env.sessions() as db:
        assert jobs.process_track(db, env.s3, env.cfg, tid) == "ready"
    t = env.track(tid)
    assert t.status == "ready" and t.error is None
    assert 7500 <= t.duration_ms <= 8600 and t.source_bitrate_kbps == 192
    assert t.hls_prefix == f"hls/{tid}" and t.cover_key == f"tracks/{tid}.jpg"
    got = keys(env, prefix=f"hls/{tid}/")
    assert f"hls/{tid}/master.m3u8" in got and f"hls/{tid}/q96/index.m3u8" in got
    assert f"hls/{tid}/q160/seg_001.ts" in got
    assert not any("/q320/" in k for k in got)  # 192k source -> no 320k rendition
    assert keys(env, env.cfg.s3_bucket_covers) == [f"tracks/{tid}.jpg"]
    ctype = env.s3.head_object(Bucket=env.cfg.s3_bucket_audio, Key=f"hls/{tid}/master.m3u8")["ContentType"]
    assert ctype == "application/vnd.apple.mpegurl"


def test_process_is_idempotent_and_skips_non_uploaded(env):
    tid = env.add_track(testing.make_audio(env.dir / "s.mp3", seconds=2))
    with env.sessions() as db:
        assert jobs.process_track(db, env.s3, env.cfg, tid) == "ready"
        assert jobs.process_track(db, env.s3, env.cfg, tid) == "skipped"  # duplicate delivery
    import uuid
    with env.sessions() as db:
        assert jobs.process_track(db, env.s3, env.cfg, uuid.uuid4()) == "skipped"  # deleted track


def run_message(env, tid, attempt=0):
    jobs.ensure_group(env.redis)
    env.redis.xadd(jobs.STREAM, {"track_id": str(tid), "attempt": str(attempt)})
    (_, msgs), = env.redis.xreadgroup(jobs.GROUP, "w1", {jobs.STREAM: ">"}, count=1)
    msg_id, fields = msgs[0]
    jobs.handle_message(env.redis, env.sessions, env.s3, env.cfg, msg_id, fields)
    return msg_id


def test_bad_file_is_retried_then_marked_failed_with_reason(env):
    junk = env.dir / "junk.mp3"
    junk.write_bytes(b"not audio" * 500)
    tid = env.add_track(junk)

    for attempt in range(jobs.MAX_ATTEMPTS - 1):
        run_message(env, tid, attempt)
        assert env.track(tid).status == "uploaded"  # reset for retry
        pending = env.redis.xrange(jobs.STREAM)
        assert len(pending) == 1 and pending[0][1]["attempt"] == str(attempt + 1)  # retry job queued
        env.redis.xtrim(jobs.STREAM, maxlen=0)  # drain so the next loop reads only its own message
    run_message(env, tid, jobs.MAX_ATTEMPTS - 1)
    t = env.track(tid)
    assert t.status == "failed" and "Not a readable media file" in t.error
    assert env.redis.xlen(jobs.STREAM) == 0  # finished jobs are removed
    assert env.redis.xpending(jobs.STREAM, jobs.GROUP)["pending"] == 0


def test_sweep_requeues_lost_jobs_but_not_queued_or_fresh_ones(env):
    old = datetime.now(UTC) - timedelta(hours=1)
    paths = [testing.make_audio(env.dir / f"{i}.mp3", seconds=1) for i in range(4)]
    lost, queued, fresh, hung = (env.add_track(p) for p in paths)
    with env.sessions() as db:
        db.execute(update(Track).where(Track.id.in_([lost, queued, hung])).values(created_at=old))
        db.execute(update(Track).where(Track.id == hung).values(
            status="processing", processing_started_at=old))
        db.commit()
    env.redis.xadd(jobs.STREAM, {"track_id": str(queued), "attempt": "0"})  # waiting in line, not lost

    assert jobs.requeue_stuck(env.redis, env.sessions) == 2  # `lost` and (reset) `hung`
    ids = sorted(f["track_id"] for _, f in env.redis.xrange(jobs.STREAM))
    assert ids == sorted(str(i) for i in (lost, queued, hung))
    assert str(fresh) not in ids
    assert env.track(hung).status == "uploaded"
    assert jobs.requeue_stuck(env.redis, env.sessions) == 0  # second sweep adds nothing


def test_long_running_track_with_old_created_at_is_not_reset(env):
    """Bulk imports: created hours ago but started processing just now must not be re-queued."""
    tid = env.add_track(testing.make_audio(env.dir / "s.mp3", seconds=1))
    with env.sessions() as db:
        db.execute(update(Track).where(Track.id == tid).values(
            status="processing", created_at=datetime.now(UTC) - timedelta(hours=5),
            processing_started_at=datetime.now(UTC)))
        db.commit()
    assert jobs.requeue_stuck(env.redis, env.sessions) == 0
    assert env.track(tid).status == "processing"


def test_malformed_job_is_dropped_not_retried(env):
    jobs.ensure_group(env.redis)
    for bad in ({"track_id": "not-a-uuid"}, {"nope": "1"}):
        env.redis.xadd(jobs.STREAM, bad)
        (_, msgs), = env.redis.xreadgroup(jobs.GROUP, "w1", {jobs.STREAM: ">"}, count=1)
        jobs.handle_message(env.redis, env.sessions, env.s3, env.cfg, *msgs[0])
    assert env.redis.xlen(jobs.STREAM) == 0
    assert env.redis.xpending(jobs.STREAM, jobs.GROUP)["pending"] == 0


def test_poll_once_idle_returns_zero_and_recovers_from_missing_group(env):
    jobs.ensure_group(env.redis)
    assert jobs.poll_once(env.redis, env.sessions, env.s3, env.cfg, "w1", block_ms=10) == 0  # idle queue is fine
    env.redis.delete(jobs.STREAM)  # simulate Redis losing state (restart without persistence)
    assert jobs.poll_once(env.redis, env.sessions, env.s3, env.cfg, "w1", block_ms=10) == 0  # NOGROUP -> recreate
    tid = env.add_track(testing.make_audio(env.dir / "p.mp3", seconds=2))
    env.redis.xadd(jobs.STREAM, {"track_id": str(tid), "attempt": "0"})
    assert jobs.poll_once(env.redis, env.sessions, env.s3, env.cfg, "w1", block_ms=10) == 1
    assert env.track(tid).status == "ready"
