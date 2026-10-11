from fastapi.testclient import TestClient

from app import jobs
from app.http import app, get_redis, get_sessions
from listens_common import testing


def client_for(env):
    app.dependency_overrides[get_redis] = lambda: env.redis
    app.dependency_overrides[get_sessions] = lambda: env.sessions
    return TestClient(app)


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_tick_drains_the_queue_and_returns_how_many_it_handled(env):
    c = client_for(env)
    try:
        src = testing.make_audio(env.dir / "s.mp3", seconds=2)
        tid = env.add_track(src)
        jobs.ensure_group(env.redis)
        env.redis.xadd(jobs.STREAM, {"track_id": str(tid), "attempt": "0"})

        r = c.post("/tick", params={"max_seconds": 10, "block_ms": 50})
        assert r.status_code == 200
        assert r.json() == {"handled": 1}
        assert env.track(tid).status == "ready"
    finally:
        app.dependency_overrides.clear()


def test_tick_on_an_empty_queue_returns_zero_quickly(env):
    c = client_for(env)
    try:
        r = c.post("/tick", params={"max_seconds": 10, "block_ms": 50})
        assert r.status_code == 200
        assert r.json() == {"handled": 0}
    finally:
        app.dependency_overrides.clear()
