from app.events import STREAM

from .test_catalogue import seed


def h(env):
    return env.headers


def test_play_start_is_published_to_the_stream(env):
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


def test_play_end_carries_ms_played(env):
    tid, *_ = seed(env, "Song")
    r = env.client.post("/events", json={"event_type": "play_end", "track_id": tid, "ms_played": 42000}, headers=h(env))
    assert r.status_code == 204
    fields = env.redis.xrange(STREAM)[0][1]
    assert fields["ms_played"] == "42000"


def test_skip_carries_position_and_reason(env):
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
