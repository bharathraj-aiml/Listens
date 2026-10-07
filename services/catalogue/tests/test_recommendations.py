import uuid
from datetime import UTC, datetime

from listens_common.models import PlayEvent, Track, TrackVector, UserVector

from .test_catalogue import seed


def h(env):
    return env.headers


def set_vector(env, model, pk, vector):
    pk = pk if isinstance(pk, uuid.UUID) else uuid.UUID(str(pk))
    with env.sessions() as db:
        if model is UserVector:
            db.add(UserVector(user_id=pk, vector=vector, trained_at=datetime.now(UTC)))
        else:
            db.add(TrackVector(track_id=pk, vector=vector, trained_at=datetime.now(UTC)))
        db.commit()


def test_made_for_you_uses_als_ranking_when_vector_present(env):
    low, *_ = seed(env, "Low score", artist="A")
    high, *_ = seed(env, "High score", artist="B")
    set_vector(env, UserVector, env.user_id, [1.0, 0.0])
    set_vector(env, TrackVector, low, [0.1, 0.0])
    set_vector(env, TrackVector, high, [1.0, 0.0])

    picks = env.client.get("/home/made-for-you", headers=h(env)).json()
    titles = [p["title"] for p in picks]
    assert titles.index("High score") < titles.index("Low score")


def test_made_for_you_als_excludes_already_played_tracks(env):
    played, *_ = seed(env, "Played", artist="A")
    fresh, *_ = seed(env, "Fresh", artist="B")
    set_vector(env, UserVector, env.user_id, [1.0])
    set_vector(env, TrackVector, played, [1.0])
    set_vector(env, TrackVector, fresh, [1.0])
    with env.sessions() as db:
        db.add(PlayEvent(user_id=env.user_id, track_id=uuid.UUID(played), event_type="play_start", occurred_at=datetime.now(UTC)))
        db.commit()

    picks = env.client.get("/home/made-for-you", headers=h(env)).json()
    titles = {p["title"] for p in picks}
    assert "Fresh" in titles and "Played" not in titles


def test_made_for_you_als_caps_two_per_artist(env):
    tids = [seed(env, f"Song {i}", artist="Same Band")[0] for i in range(4)]
    set_vector(env, UserVector, env.user_id, [1.0])
    for t in tids:
        set_vector(env, TrackVector, t, [1.0])

    picks = env.client.get("/home/made-for-you?limit=10", headers=h(env)).json()
    assert len(picks) == 2  # only 2 from "Same Band" allowed, no other tracks exist to fill the rest


def test_similar_tracks_ranks_by_vector_cosine_similarity(env):
    target, *_ = seed(env, "Target")
    close, *_ = seed(env, "Close")
    far, *_ = seed(env, "Far")
    set_vector(env, TrackVector, target, [1.0, 0.0])
    set_vector(env, TrackVector, close, [0.9, 0.1])
    set_vector(env, TrackVector, far, [0.0, 1.0])

    out = env.client.get(f"/tracks/{target}/similar", headers=h(env)).json()
    titles = [t["title"] for t in out]
    assert titles == ["Close", "Far"]


def test_similar_tracks_cold_start_uses_tempo_energy_distance(env):
    target, *_ = seed(env, "Target")
    close, *_ = seed(env, "Close")
    far, *_ = seed(env, "Far")
    with env.sessions() as db:
        db.get(Track, uuid.UUID(target)).tempo_bpm, db.get(Track, uuid.UUID(target)).energy = 120.0, 0.5
        db.get(Track, uuid.UUID(close)).tempo_bpm, db.get(Track, uuid.UUID(close)).energy = 122.0, 0.52
        db.get(Track, uuid.UUID(far)).tempo_bpm, db.get(Track, uuid.UUID(far)).energy = 60.0, 0.05
        db.commit()

    out = env.client.get(f"/tracks/{target}/similar", headers=h(env)).json()
    titles = [t["title"] for t in out]
    assert titles[0] == "Close"


def test_similar_tracks_falls_back_to_same_artist_when_no_vector_or_features(env):
    target, _artist_id, _ = seed(env, "Target", artist="Shared Band")
    sibling, *_ = seed(env, "Sibling", artist="Shared Band")
    stranger, *_ = seed(env, "Stranger", artist="Other Band")

    out = env.client.get(f"/tracks/{target}/similar", headers=h(env)).json()
    titles = {t["title"] for t in out}
    assert "Sibling" in titles
