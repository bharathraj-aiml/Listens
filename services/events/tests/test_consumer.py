import uuid
from datetime import UTC, datetime

from app import consumer
from listens_common.models import PlayEvent


def push(env, **fields):
    consumer.ensure_group(env.redis)
    env.redis.xadd(consumer.STREAM, {"attempt": "0", **fields})
    (_, msgs), = env.redis.xreadgroup(consumer.GROUP, "w1", {consumer.STREAM: ">"}, count=1)
    return msgs[0]


def base_fields(**overrides):
    f = {
        "event_type": "play_start",
        "user_id": str(uuid.uuid4()),
        "track_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    f.update(overrides)
    return f


def test_play_start_is_inserted(env):
    msg_id, fields = push(env, **base_fields())
    consumer.handle_message(env.redis, env.sessions_, msg_id, fields)
    with env.sessions_() as db:
        rows = db.query(PlayEvent).all()
        assert len(rows) == 1
        assert rows[0].event_type == "play_start"
        assert rows[0].ms_played is None and rows[0].position_ms is None


def test_play_end_with_ms_played(env):
    msg_id, fields = push(env, **base_fields(event_type="play_end", ms_played="45000"))
    consumer.handle_message(env.redis, env.sessions_, msg_id, fields)
    with env.sessions_() as db:
        row = db.query(PlayEvent).one()
        assert row.event_type == "play_end" and row.ms_played == 45000


def test_skip_with_position_and_reason(env):
    msg_id, fields = push(env, **base_fields(event_type="skip", position_ms="12000", reason="next_button"))
    consumer.handle_message(env.redis, env.sessions_, msg_id, fields)
    with env.sessions_() as db:
        row = db.query(PlayEvent).one()
        assert row.event_type == "skip" and row.position_ms == 12000 and row.reason == "next_button"


def test_unknown_event_type_is_retried_once(env):
    msg_id, fields = push(env, **base_fields(event_type="bogus", attempt="0"))
    consumer.handle_message(env.redis, env.sessions_, msg_id, fields)
    with env.sessions_() as db:
        assert db.query(PlayEvent).count() == 0
    remaining = env.redis.xrange(consumer.STREAM)
    assert len(remaining) == 1 and remaining[0][1]["attempt"] == "1"  # re-queued for another try
    assert env.redis.xpending(consumer.STREAM, consumer.GROUP)["pending"] == 0  # original message acked+removed


def test_unknown_event_type_dropped_after_max_attempts(env):
    msg_id, fields = push(env, **base_fields(event_type="bogus", attempt=str(consumer.MAX_ATTEMPTS - 1)))
    consumer.handle_message(env.redis, env.sessions_, msg_id, fields)
    with env.sessions_() as db:
        assert db.query(PlayEvent).count() == 0
    assert env.redis.xlen(consumer.STREAM) == 0  # not retried again: give up for good
    assert env.redis.xpending(consumer.STREAM, consumer.GROUP)["pending"] == 0


def test_malformed_message_missing_fields_does_not_crash_the_consumer(env):
    consumer.ensure_group(env.redis)
    env.redis.xadd(consumer.STREAM, {"event_type": "play_start"})  # missing user_id/track_id/occurred_at
    (_, msgs), = env.redis.xreadgroup(consumer.GROUP, "w1", {consumer.STREAM: ">"}, count=1)
    consumer.handle_message(env.redis, env.sessions_, *msgs[0])  # must not raise
    with env.sessions_() as db:
        assert db.query(PlayEvent).count() == 0


def test_poll_once_processes_a_batch(env):
    consumer.ensure_group(env.redis)
    for _ in range(3):
        env.redis.xadd(consumer.STREAM, {**base_fields(), "attempt": "0"})
    handled = consumer.poll_once(env.redis, env.sessions_, "w1", block_ms=10)
    assert handled == 3
    with env.sessions_() as db:
        assert db.query(PlayEvent).count() == 3


def test_poll_once_recovers_from_missing_group(env):
    consumer.ensure_group(env.redis)
    env.redis.delete(consumer.STREAM)
    assert consumer.poll_once(env.redis, env.sessions_, "w1", block_ms=10) == 0  # NOGROUP -> recreate, no crash


def test_sweep_reclaims_abandoned_messages(env):
    consumer.ensure_group(env.redis)
    env.redis.xadd(consumer.STREAM, {**base_fields(), "attempt": "0"})
    # a different, now-dead consumer reads it but never acks
    env.redis.xreadgroup(consumer.GROUP, "dead-consumer", {consumer.STREAM: ">"}, count=1)
    assert env.redis.xpending(consumer.STREAM, consumer.GROUP)["pending"] == 1
    consumer.CLAIM_IDLE_MS = 0  # claim immediately for the test instead of waiting 5 minutes
    consumer.sweep(env.redis, env.sessions_, "w2")
    with env.sessions_() as db:
        assert db.query(PlayEvent).count() == 1
    assert env.redis.xpending(consumer.STREAM, consumer.GROUP)["pending"] == 0
