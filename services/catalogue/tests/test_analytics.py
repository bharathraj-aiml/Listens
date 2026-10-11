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


def test_listening_stats_this_week_top_artist_and_track(env):
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.isoweekday() - 1)
    mid_week = datetime.combine(monday + timedelta(days=2), datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)

    tid_a, *_ = seed(env, "Song A", artist="Artist A")
    tid_b, *_ = seed(env, "Song B", artist="Artist B")
    for _ in range(3):  # Artist A: 3 play_starts -> top artist
        event(env, env.user_id, tid_a, "play_start", occurred_at=mid_week)
    event(env, env.user_id, tid_b, "play_start", occurred_at=mid_week)
    for _ in range(2):  # Song A: 2 verified streams -> top track
        event(env, env.user_id, tid_a, "play_end", ms_played=40_000, occurred_at=mid_week)

    out = env.client.get("/analytics/listening-stats?range=this_week", headers=h(env)).json()
    assert out["top_artist"]["artist"]["name"] == "Artist A"
    assert out["top_artist"]["play_count"] == 3
    assert out["top_track"]["track"]["title"] == "Song A"
    assert out["top_track"]["stream_count"] == 2


def test_listening_stats_last_week_excludes_this_weeks_plays(env):
    tid, *_ = seed(env, "Recent")
    event(env, env.user_id, tid, "play_start")  # occurs now -> this week, not last week
    out = env.client.get("/analytics/listening-stats?range=last_week", headers=h(env)).json()
    assert out["top_artist"] is None and out["top_track"] is None


def test_recents_groups_by_day_with_most_played_as_cover(env):
    tid_a, *_ = seed(env, "Morning Song")
    tid_b, *_ = seed(env, "Evening Song")
    today = datetime.now(UTC)
    event(env, env.user_id, tid_a, "play_start", occurred_at=today)
    event(env, env.user_id, tid_a, "play_start", occurred_at=today)
    event(env, env.user_id, tid_b, "play_start", occurred_at=today)
    event(env, env.user_id, tid_a, "play_start", occurred_at=today - timedelta(days=1))

    out = env.client.get("/analytics/recents", headers=h(env)).json()
    assert out[0]["play_count"] == 3  # today: 2 (Morning) + 1 (Evening)
    assert out[0]["cover_track"]["title"] == "Morning Song"  # today's most-played
    assert out[1]["play_count"] == 1  # yesterday


def test_analytics_requires_auth(env):
    assert env.client.get("/analytics/listening-stats").status_code == 401
    assert env.client.get("/analytics/recents").status_code == 401
