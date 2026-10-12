import pytest
from app.events import STREAM
from app.main import app
from listens_common.config import get_settings
from listens_common.db import get_db
from listens_common.models import PlayEvent
from sqlalchemy import select

from .test_catalogue import seed


def h(env):
    return env.headers


@pytest.fixture
def queue_mode():
    """EVENTS_VIA_QUEUE=true: the original design, every event goes to the Redis stream."""
    s = get_settings()
    s.events_via_queue = True
    yield
    s.events_via_queue = False


def stored(env):
    with env.sessions() as db:
        return list(db.scalars(select(PlayEvent).order_by(PlayEvent.id)))


def test_event_is_written_straight_to_the_database(env):
    tid, *_ = seed(env, "Song")
    r = env.client.post("/events", json={"event_type": "play_start", "track_id": tid, "session_id": "abc"}, headers=h(env))
    assert r.status_code == 204
    rows = stored(env)
    assert len(rows) == 1 and str(rows[0].track_id) == tid and rows[0].user_id == env.user_id
    assert rows[0].event_type == "play_start" and rows[0].session_id == "abc" and rows[0].occurred_at is not None
    assert env.redis.xrange(STREAM) == []  # nothing left for the consumer: no daily job needed


def test_skip_and_play_end_fields_are_stored(env):
    tid, *_ = seed(env, "Song")
    env.client.post("/events", json={"event_type": "skip", "track_id": tid, "position_ms": 5000, "reason": "next_button"}, headers=h(env))
    env.client.post("/events", json={"event_type": "play_end", "track_id": tid, "ms_played": 42000}, headers=h(env))
    skip, end = stored(env)
    assert (skip.position_ms, skip.reason) == (5000, "next_button") and end.ms_played == 42000


def test_falls_back_to_the_queue_when_the_database_write_fails(env):
    tid, *_ = seed(env, "Song")

    class Broken:
        def add(self, *_):
            raise RuntimeError("database asleep")

        def commit(self):
            raise RuntimeError("database asleep")

        def rollback(self):
            pass

    app.dependency_overrides[get_db] = lambda: Broken()
    try:
        r = env.client.post("/events", json={"event_type": "play_start", "track_id": tid}, headers=h(env))
    finally:
        pass  # the env fixture clears every override at teardown
    assert r.status_code == 204
    jobs = env.redis.xrange(STREAM)
    assert len(jobs) == 1 and jobs[0][1]["track_id"] == tid  # the event was handed to the queue, not lost


def test_play_start_is_published_to_the_stream(env, queue_mode):
    tid, *_ = seed(env, "Song")
    r = env.client.post("/events", json={"event_type": "play_start", "track_id": tid}, headers=h(env))
    assert r.status_code == 204
    jobs = env.redis.xrange(STREAM)
    assert len(jobs) == 1
    fields = jobs[0][1]
    assert fields["event_type"] == "play_start"
    assert fields["track_id"] == tid
    assert fields["user_id"] == str(env.user_id)
    assert "occurred_at" in fields
    assert "ms_played" not in fields and "reason" not in fields  # omitted, not sent as empty strings


def test_play_end_carries_ms_played(env, queue_mode):
    tid, *_ = seed(env, "Song")
    r = env.client.post("/events", json={"event_type": "play_end", "track_id": tid, "ms_played": 42000}, headers=h(env))
    assert r.status_code == 204
    fields = env.redis.xrange(STREAM)[0][1]
    assert fields["ms_played"] == "42000"


def test_skip_carries_position_and_reason(env, queue_mode):
    tid, *_ = seed(env, "Song")
    r = env.client.post(
        "/events", json={"event_type": "skip", "track_id": tid, "position_ms": 5000, "reason": "next_button"}, headers=h(env)
    )
    assert r.status_code == 204
    fields = env.redis.xrange(STREAM)[0][1]
    assert fields["position_ms"] == "5000" and fields["reason"] == "next_button"


def test_rejects_unknown_event_type(env):
    tid, *_ = seed(env, "Song")
    r = env.client.post("/events", json={"event_type": "like", "track_id": tid}, headers=h(env))
    assert r.status_code == 422  # not a client-submittable type (see events.py docstring)


def test_does_not_validate_track_existence(env):
    """By design (see events.py): this is a hot-path, fire-and-forget log, not a mutation -
    an unknown track_id just produces a harmless analytics row for nothing, same tradeoff as
    play_events having no foreign key at all."""
    import uuid
    r = env.client.post("/events", json={"event_type": "play_start", "track_id": str(uuid.uuid4())}, headers=h(env))
    assert r.status_code == 204


def test_requires_auth(env):
    import uuid
    r = env.client.post("/events", json={"event_type": "play_start", "track_id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_liking_a_track_publishes_a_like_event(env):
    tid, *_ = seed(env, "Song")
    env.client.post(f"/likes/{tid}", headers=h(env))
    jobs = env.redis.xrange(STREAM)
    assert len(jobs) == 1 and jobs[0][1]["event_type"] == "like" and jobs[0][1]["track_id"] == tid


def test_liking_an_already_liked_track_does_not_republish(env):
    tid, *_ = seed(env, "Song")
    env.client.post(f"/likes/{tid}", headers=h(env))
    env.client.post(f"/likes/{tid}", headers=h(env))  # idempotent like
    assert len(env.redis.xrange(STREAM)) == 1


def test_adding_to_playlist_publishes_an_event(env):
    tid, *_ = seed(env, "Song")
    pl = env.client.post("/playlists", json={"name": "P"}, headers=h(env)).json()
    env.client.post(f"/playlists/{pl['id']}/tracks", json={"track_id": tid}, headers=h(env))
    jobs = env.redis.xrange(STREAM)
    assert len(jobs) == 1 and jobs[0][1]["event_type"] == "add_to_playlist" and jobs[0][1]["track_id"] == tid
