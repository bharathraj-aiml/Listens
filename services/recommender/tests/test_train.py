import numpy as np
from sqlalchemy import select

from app import train
from listens_common.models import TrackVector, UserVector


def test_train_with_no_data_returns_zero_and_writes_nothing(env):
    with env.sessions_() as db:
        assert train.train(db) == 0
        assert db.scalars(select(UserVector)).first() is None
        assert db.scalars(select(TrackVector)).first() is None


def test_train_persists_vectors_for_users_and_tracks_with_data(env):
    u, t = env.user(), env.track()
    env.like(u, t)
    with env.sessions_() as db:
        n = train.train(db)
        assert n == 1
        uv = db.get(UserVector, u)
        tv = db.get(TrackVector, t)
        assert uv is not None and len(uv.vector) == train.FACTORS
        assert tv is not None and len(tv.vector) == train.FACTORS
        assert uv.trained_at is not None


def test_retrain_replaces_rather_than_accumulates(env):
    u1, t1 = env.user(), env.track()
    env.like(u1, t1)
    with env.sessions_() as db:
        train.train(db)

    u2, t2 = env.user(), env.track()
    env.like(u2, t2)
    with env.sessions_() as db:
        train.train(db)
        all_users = db.scalars(select(UserVector)).all()
        all_tracks = db.scalars(select(TrackVector)).all()
    # both rounds' users/tracks still have interaction data, so both carry over - but there
    # must be exactly one row each, not duplicates from the first training run.
    assert {v.user_id for v in all_users} == {u1, u2}
    assert {v.track_id for v in all_tracks} == {t1, t2}


def test_recommendation_score_prefers_the_liked_cluster(env):
    """Block-structure correctness check: three users who only like "pop" tracks, three who
    only like "rock" tracks. A well-trained factorization should place each cluster's user
    vectors closer (higher dot product) to their own cluster's track vectors than the other's -
    this is the same dot-product scoring the catalogue service will use for recommendations."""
    pop_tracks = [env.track() for _ in range(3)]
    rock_tracks = [env.track() for _ in range(3)]
    pop_fans = [env.user() for _ in range(4)]
    rock_fans = [env.user() for _ in range(4)]
    for u in pop_fans:
        for t in pop_tracks:
            env.like(u, t)
    for u in rock_fans:
        for t in rock_tracks:
            env.like(u, t)

    with env.sessions_() as db:
        train.train(db)
        user_vecs = {v.user_id: np.array(v.vector) for v in db.scalars(select(UserVector)).all()}
        track_vecs = {v.track_id: np.array(v.vector) for v in db.scalars(select(TrackVector)).all()}

    for u in pop_fans:
        pop_score = np.mean([user_vecs[u] @ track_vecs[t] for t in pop_tracks])
        rock_score = np.mean([user_vecs[u] @ track_vecs[t] for t in rock_tracks])
        assert pop_score > rock_score
    for u in rock_fans:
        pop_score = np.mean([user_vecs[u] @ track_vecs[t] for t in pop_tracks])
        rock_score = np.mean([user_vecs[u] @ track_vecs[t] for t in rock_tracks])
        assert rock_score > pop_score
