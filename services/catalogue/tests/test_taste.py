import uuid
from datetime import UTC, date, datetime

import numpy as np

from app import taste
from listens_common.models import Album, Artist, ArtistMeta, Like, Track

from .test_catalogue import seed


def h(env):
    return env.headers


def item(**kw):
    return taste.Item(id=uuid.uuid4(), artist_id=kw.pop("artist_id", uuid.uuid4()), **kw)


# ---------------------------------------------------------------- language

def test_detect_language_tamil_script_romanised_and_other():
    assert taste.detect_language("வாத்தி கமிங்", "அனிருத்") == "ta"
    assert taste.detect_language("Vaathi Coming", "Anirudh Ravichander") is None  # romanised: unknown, not guessed
    assert taste.detect_language("तुम ही हो", "अरिजीत") == "other"
    assert taste.detect_language("a", None) is None  # too little text to say


# -------------------------------------------------------------- similarity

def test_same_film_and_era_outscores_an_unrelated_song():
    lib = taste.Library([])
    film = "leo"
    a = item(album_key=film, year=2023, language="ta", tempo=120, energy=0.4)
    same_film = item(album_key=film, year=2023, language="ta", tempo=118, energy=0.42)
    other = item(album_key='roja', year=1994, language="other", tempo=70, energy=0.1)
    assert lib.similarity(a, same_film) > 0.8
    assert lib.similarity(a, other) < 0.3


def test_half_or_double_tempo_counts_as_a_match():
    lib = taste.Library([])
    a, double, off = item(tempo=70), item(tempo=140), item(tempo=100)
    assert lib.similarity(a, double) > lib.similarity(a, off)


def test_one_weak_shared_signal_is_not_called_similar():
    lib = taste.Library([])
    assert lib.similarity(item(genre="Pop"), item(genre="pop")) < 0.15


def test_unrelated_artists_with_a_common_neighbour_are_close_without_a_direct_link():
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    artists = {
        a_id: taste.ArtistInfo(mbid="A", neighbours={"HUB": 1.0, "X": 0.5}),
        b_id: taste.ArtistInfo(mbid="B", neighbours={"HUB": 0.9, "Y": 0.4}),
        c_id: taste.ArtistInfo(mbid="C", neighbours={"Z": 1.0}),
    }
    lib = taste.Library([], artists)
    near = lib.artist_affinity(item(artist_id=a_id), item(artist_id=b_id))
    far = lib.artist_affinity(item(artist_id=a_id), item(artist_id=c_id))
    assert near > 0.3 and far == 0.0


def test_a_direct_listening_link_is_strong_and_artists_without_data_are_unknown():
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    lib = taste.Library([], {a_id: taste.ArtistInfo(mbid="A", neighbours={"B": 1.0}), b_id: taste.ArtistInfo(mbid="B")})
    assert lib.artist_affinity(item(artist_id=a_id), item(artist_id=b_id)) == 1.0
    assert lib.artist_affinity(item(artist_id=a_id), item(artist_id=uuid.uuid4())) is None


def test_standardise_needs_a_spread_and_equalises_dimensions():
    ids = [uuid.uuid4() for _ in range(4)]
    assert taste.Library.standardise({ids[0]: [1.0, 1000.0], ids[1]: [2.0, 2000.0]}) == {}
    out = taste.Library.standardise({i: [float(k), 1000.0 * k + (k % 2)] for k, i in enumerate(ids)})
    assert all(abs(np.linalg.norm(v) - 1) < 1e-9 for v in out.values())


# --------------------------------------------------------------- taste/MMR

def _lib_with_vectors():
    liked = item(vec=np.array([1.0, 0.0]))
    close = item(vec=np.array([0.95, 0.31]))
    far = item(vec=np.array([0.0, 1.0]))
    return taste.Library([liked, close, far]), liked, close, far


def test_taste_prefers_tracks_near_what_was_liked_and_avoids_skipped_ones():
    lib, liked, close, far = _lib_with_vectors()
    weights = {liked.id: 3.0}
    assert taste.taste_score(lib, close, weights) > taste.taste_score(lib, far, weights)
    skipped = {liked.id: 3.0, far.id: -4.0}
    assert taste.taste_score(lib, far, skipped) <= taste.taste_score(lib, far, weights)
    assert taste.taste_score(lib, close, {}) is None


def test_mmr_caps_per_artist_and_prefers_variety():
    artist = uuid.uuid4()
    clones = [item(artist_id=artist, vec=np.array([1.0, 0.0])) for _ in range(4)]
    different = item(vec=np.array([0.0, 1.0]))
    lib = taste.Library([*clones, different])
    scores = {c.id: 0.9 for c in clones} | {different.id: 0.8}
    picked = taste.mmr(lib, scores, limit=3)
    assert different.id in picked
    assert sum(lib.items[p].artist_id == artist for p in picked) <= 2


# ------------------------------------------------------------- through the API

def _meta(env, artist_id, mbid, similar):
    with env.sessions() as db:
        db.add(ArtistMeta(artist_id=uuid.UUID(artist_id), mbid=mbid, tags={}, similar=similar,
                          fetched_at=datetime.now(UTC)))
        db.commit()


def test_similar_uses_the_open_data_artist_graph(env):
    seed_t, a1, _ = seed(env, "Seed", artist="Anirudh")
    friend_t, a2, _ = seed(env, "Friend", artist="Sid Sriram")
    stranger_t, a3, _ = seed(env, "Stranger", artist="Someone Else")
    _meta(env, a1, "mb-anirudh", [{"mbid": "mb-sid", "name": "Sid Sriram", "score": 103}])
    _meta(env, a2, "mb-sid", [{"mbid": "mb-anirudh", "name": "Anirudh", "score": 100}])
    _meta(env, a3, "mb-else", [{"mbid": "mb-nobody", "name": "N", "score": 10}])

    titles = [t["title"] for t in env.client.get(f"/tracks/{seed_t}/similar", headers=h(env)).json()]
    assert titles.index("Friend") < titles.index("Stranger")


def test_similar_prefers_the_same_film_soundtrack(env):
    seed_t, *_ = seed(env, "Opening", artist="Composer A", album="Film One")
    same_film, *_ = seed(env, "Song Two", artist="Singer B", album="Film One")
    other_film, *_ = seed(env, "Song Three", artist="Singer C", album="Film Two")
    titles = [t["title"] for t in env.client.get(f"/tracks/{seed_t}/similar", headers=h(env)).json()]
    assert titles[0] == "Song Two"


def test_made_for_you_follows_taste_through_the_artist_graph(env):
    liked_t, a_liked, _ = seed(env, "Liked Song", artist="Liked Artist")
    near_t, a_near, _ = seed(env, "Near Song", artist="Related Artist")
    far_t, a_far, _ = seed(env, "Far Song", artist="Unrelated Artist")
    _meta(env, a_liked, "mb-l", [{"mbid": "mb-r", "name": "R", "score": 90}])
    _meta(env, a_near, "mb-r", [{"mbid": "mb-l", "name": "L", "score": 90}])
    _meta(env, a_far, "mb-f", [{"mbid": "mb-q", "name": "Q", "score": 90}])
    with env.sessions() as db:
        db.add(Like(user_id=env.user_id, track_id=uuid.UUID(liked_t)))
        db.commit()

    titles = [t["title"] for t in env.client.get("/home/made-for-you", headers=h(env)).json()]
    assert titles.index("Near Song") < titles.index("Far Song")


def test_era_and_language_shape_similarity_for_tamil_titles(env):
    with env.sessions() as db:
        artist = Artist(name="Composer")
        db.add(artist)
        db.flush()
        old = Album(title="Old Film", artist_id=artist.id, release_date=date(1995, 1, 1))
        new = Album(title="New Film", artist_id=artist.id, release_date=date(2023, 1, 1))
        db.add_all([old, new])
        db.flush()
        mk = lambda title, alb: Track(artist_id=artist.id, album_id=alb.id, title=title, status="ready",
                                      uploader_id=env.user_id, duration_ms=1000)
        seed_track, same_era, other_era = mk("வானம்", new), mk("நிலா", new), mk("Old Gold", old)
        db.add_all([seed_track, same_era, other_era])
        db.commit()
        seed_id = str(seed_track.id)

    titles = [t["title"] for t in env.client.get(f"/tracks/{seed_id}/similar", headers=h(env)).json()]
    assert titles[0] == "நிலா"


def test_a_joint_credit_is_linked_to_each_person_named_in_it():
    joint, solo, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lib = taste.Library([], {
        joint: taste.ArtistInfo(mbid="rahman", extra_mbids=("hari",), neighbours={"x": 1.0}),
        solo: taste.ArtistInfo(mbid="hari", neighbours={"y": 1.0}),
        other: taste.ArtistInfo(mbid="zzz", neighbours={"q": 1.0}),
    })
    mk = lambda artist: taste.Item(id=uuid.uuid4(), artist_id=artist)
    assert lib.artist_affinity(mk(joint), mk(solo)) > 0.3  # shares Hariharan
    assert lib.artist_affinity(mk(joint), mk(other)) == 0.0
