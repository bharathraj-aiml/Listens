import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app import consumer
from app.http import app, get_redis, get_sessions
from listens_common.models import PlayEvent


def client_for(env):
    app.dependency_overrides[get_redis] = lambda: env.redis
    app.dependency_overrides[get_sessions] = lambda: env.sessions_
    return TestClient(app)


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_tick_drains_queued_events_and_inserts_them(env):
    c = client_for(env)
    try:
        env.redis.xadd(consumer.STREAM, {
            "attempt": "0", "event_type": "play_start",
            "user_id": str(uuid.uuid4()), "track_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
        })
        r = c.post("/tick", params={"max_seconds": 5, "block_ms": 50})
        assert r.status_code == 200
        assert r.json() == {"handled": 1}
        with env.sessions_() as db:
            assert db.query(PlayEvent).count() == 1
    finally:
        app.dependency_overrides.clear()


def test_tick_on_an_empty_stream_returns_zero_quickly(env):
    c = client_for(env)
    try:
        r = c.post("/tick", params={"max_seconds": 5, "block_ms": 50})
        assert r.status_code == 200
        assert r.json() == {"handled": 0}
    finally:
        app.dependency_overrides.clear()
