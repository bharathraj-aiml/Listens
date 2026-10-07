from app import matrix


def test_no_data_returns_none(env):
    with env.sessions_() as db:
        assert matrix.build(db) is None


def test_full_listen_weight(env):
    u, t = env.user(), env.track(duration_ms=200_000)
    env.play(u, t, "play_end", ms_played=190_000)  # >= 90% of duration: a full listen
    with env.sessions_() as db:
        m = matrix.build(db)
    assert m.user_ids == [u] and m.track_ids == [t]
    assert m.csr[0, 0] == matrix.FULL_LISTEN_WEIGHT


def test_repeat_listens_add_bonus_weight(env):
    u, t = env.user(), env.track(duration_ms=200_000)
    for _ in range(3):
        env.play(u, t, "play_end", ms_played=190_000)
    with env.sessions_() as db:
        m = matrix.build(db)
    # 3 full listens: 3*1 (base) + 2*2 (two repeats beyond the first) = 7
    assert m.csr[0, 0] == 3 * matrix.FULL_LISTEN_WEIGHT + 2 * matrix.REPEAT_LISTEN_WEIGHT


def test_partial_listen_is_not_a_full_listen(env):
    u, t = env.user(), env.track(duration_ms=200_000)
    env.play(u, t, "play_end", ms_played=50_000)  # well under 90%
    with env.sessions_() as db:
        assert matrix.build(db) is None


def test_save_weight_from_like_and_playlist_add(env):
    u, t = env.user(), env.track()
    env.like(u, t)
    env.add_to_playlist(u, t)
    with env.sessions_() as db:
        m = matrix.build(db)
    assert m.csr[0, 0] == 2 * matrix.SAVE_WEIGHT


def test_early_skip_reduces_weight_but_clamps_at_zero(env):
    u, t = env.user(), env.track()
    env.like(u, t)  # +3
    env.play(u, t, "skip", position_ms=5_000)  # -2 -> net +1, still present
    with env.sessions_() as db:
        m = matrix.build(db)
    assert m.csr[0, 0] == matrix.SAVE_WEIGHT + matrix.EARLY_SKIP_WEIGHT


def test_pure_early_skips_clamp_to_zero_and_vanish(env):
    u, t = env.user(), env.track()
    env.play(u, t, "skip", position_ms=1_000)
    env.play(u, t, "skip", position_ms=2_000)
    with env.sessions_() as db:
        assert matrix.build(db) is None  # negative weight clamped to 0 -> no entry at all


def test_late_skip_is_not_an_early_skip(env):
    u, t = env.user(), env.track()
    env.like(u, t)
    env.play(u, t, "skip", position_ms=45_000)  # past EARLY_SKIP_MS: not penalized
    with env.sessions_() as db:
        m = matrix.build(db)
    assert m.csr[0, 0] == matrix.SAVE_WEIGHT


def test_matrix_shape_covers_all_users_and_tracks(env):
    u1, u2 = env.user(), env.user()
    t1, t2 = env.track(), env.track()
    env.like(u1, t1)
    env.like(u2, t2)
    with env.sessions_() as db:
        m = matrix.build(db)
    assert sorted(m.user_ids) == sorted([u1, u2])
    assert sorted(m.track_ids) == sorted([t1, t2])
    assert m.csr.shape == (2, 2)
