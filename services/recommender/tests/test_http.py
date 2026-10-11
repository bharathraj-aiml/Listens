from fastapi.testclient import TestClient

from app.http import app, get_sessions


def client_for(env):
    app.dependency_overrides[get_sessions] = lambda: env.sessions_
    return TestClient(app)


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_tick_runs_a_training_pass_with_no_data(env):
    c = client_for(env)
    try:
        r = c.post("/tick")
        assert r.status_code == 200
        assert r.json() == {"trained": True}
    finally:
        app.dependency_overrides.clear()
