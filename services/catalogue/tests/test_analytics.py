import uuid
from datetime import UTC, datetime, timedelta

from listens_common.models import PlayEvent

from .test_catalogue import seed


def h(env):
    return env.headers


def event(env, user_id, track_id, event_type, *, ms_played=None, occurred_at=None):
    with env.sessions() as db:
        db.add(PlayEvent(
            user_id=user_id, track_id=uuid.UUID(str(track_id)), event_type=event_type,
            ms_played=ms_played, occurred_at=occurred_at or datetime.now(UTC),
        ))
        db.commit()


def test_top_tracks_only_counts_plays_past_the_30s_threshold(env):
    long_play, *_ = seed(env, "Long Play")
    short_play, *_ = seed(env, "Short Play")
    event(env, env.user_id, long_play, "play_end", ms_played=45_000)
    event(env, env.user_id, long_play, "play_end", ms_played=60_000)
    event(env, env.user_id, short_play, "play_end", ms_played=5_000)  # under threshold: doesn't count

    out = env.client.get("/analytics/top-tracks", headers=h(env)).json()
    assert [(o["track"]["title"], o["stream_count"]) for o in out] == [("Long Play", 2)]


def test_top_tracks_ordered_by_stream_count_desc(env):
    a, *_ = seed(env, "A")
    b, *_ = seed(env, "B")
    for _ in range(3):
        event(env, env.user_id, a, "play_end", ms_played=40_000)
    event(env, env.user_id, b, "play_end", ms_played=40_000)
    titles = [o["track"]["title"] for o in env.client.get("/analytics/top-tracks", headers=h(env)).json()]
    assert titles == ["A", "B"]


def test_top_tracks_is_per_user(env):
    tid, *_ = seed(env, "Mine")
    event(env, env.user_id, tid, "play_end", ms_played=40_000)
    assert env.client.get("/analytics/top-tracks", headers=env.other_headers).json() == []
    assert len(env.client.get("/analytics/top-tracks", headers=h(env)).json()) == 1


def test_skip_rate_requires_minimum_plays_and_sorts_highest_first(env):
    one_play_one_skip, *_ = seed(env, "Too few plays")  # 1 play, below the minimum: excluded
    event(env, env.user_id, one_play_one_skip, "play_start")
    event(env, env.user_id, one_play_one_skip, "skip")

    mostly_skipped, *_ = seed(env, "Mostly skipped")
    for _ in range(3):
        event(env, env.user_id, mostly_skipped, "play_start")
    for _ in range(2):
        event(env, env.user_id, mostly_skipped, "skip")  # 2/3 skipped

    rarely_skipped, *_ = seed(env, "Rarely skipped")
    for _ in range(4):
        event(env, env.user_id, rarely_skipped, "play_start")
    event(env, env.user_id, rarely_skipped, "skip")  # 1/4 skipped

    out = env.client.get("/analytics/skip-rate", headers=h(env)).json()
    titles = [o["track"]["title"] for o in out]
    assert titles == ["Mostly skipped", "Rarely skipped"]  # "Too few plays" excluded, highest rate first
    assert out[0]["play_count"] == 3 and out[0]["skip_count"] == 2 and out[0]["skip_rate"] == 0.6667


def test_listening_by_hour_covers_all_24_hours_with_zero_fill(env):
    tid, *_ = seed(env, "Song")
    event(env, env.user_id, tid, "play_start", occurred_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC))
    event(env, env.user_id, tid, "play_start", occurred_at=datetime(2026, 1, 2, 9, 45, tzinfo=UTC))
    event(env, env.user_id, tid, "play_start", occurred_at=datetime(2026, 1, 1, 22, 0, tzinfo=UTC))

    out = env.client.get("/analytics/listening-by-hour", headers=h(env)).json()
    assert len(out) == 24
    by_hour = {o["hour"]: o["count"] for o in out}
    assert by_hour[9] == 2 and by_hour[22] == 1 and by_hour[0] == 0


def test_analytics_requires_auth(env):
    assert env.client.get("/analytics/top-tracks").status_code == 401
    assert env.client.get("/analytics/skip-rate").status_code == 401
    assert env.client.get("/analytics/listening-by-hour").status_code == 401
