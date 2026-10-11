import uuid

from app import taste
from listens_common import tamil_seed

from .test_catalogue import seed


def h(env):
    return env.headers


def test_lookup_matches_aliases_case_dots_and_spacing():
    for credit in ("SPB", "S.P.B", "s. p. balasubrahmanyam", "S P Balasubrahmanyam"):
        assert tamil_seed.lookup(credit).name == "S. P. Balasubrahmanyam", credit
    for credit in ("AR Rahman", "A.R. Rahman", "a r rahman"):
        assert tamil_seed.lookup(credit).name == "A. R. Rahman", credit
    assert tamil_seed.lookup("ilayaraja").name == "Ilaiyaraaja"


def test_joint_credits_match_on_any_named_part():
    assert tamil_seed.lookup("Mano, S. Janaki").name == "Mano"
    assert tamil_seed.lookup("Some Unknown Singer & S. Janaki").name == "S. Janaki"
    assert tamil_seed.lookup("K. S. Chithra feat. Someone").name == "K. S. Chithra"


def test_lookup_does_not_match_lookalikes_or_empty():
    assert tamil_seed.lookup("Alex") is None
    assert tamil_seed.lookup("Rahmania") is None
    assert tamil_seed.lookup("Arijit Singh") is None
    assert tamil_seed.lookup("") is None and tamil_seed.lookup(None) is None


def test_eras_and_circles_separate_the_90s_from_today():
    janaki, anirudh = tamil_seed.lookup("S. Janaki"), tamil_seed.lookup("Anirudh")
    assert janaki.circle == tamil_seed.CLASSIC and anirudh.circle == tamil_seed.MODERN
    assert janaki.year < 2000 < anirudh.year
    assert tamil_seed.lookup("Ilaiyaraaja").tamil_core and not tamil_seed.lookup("SPB").tamil_core


def test_same_circle_gives_a_baseline_affinity_with_no_listening_data():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lib = taste.Library([], {
        a: taste.ArtistInfo(circle="classic"), b: taste.ArtistInfo(circle="classic"), c: taste.ArtistInfo(circle="modern"),
    })
    mk = lambda artist: taste.Item(id=uuid.uuid4(), artist_id=artist)
    assert lib.artist_affinity(mk(a), mk(b)) == taste.CIRCLE_AFFINITY
    assert lib.artist_affinity(mk(a), mk(c)) is None


def test_90s_song_recommends_other_90s_singers_before_modern_ones(env):
    seed_t, *_ = seed(env, "Raja Raja", artist="Ilaiyaraaja")
    seed(env, "Modern Hit", artist="Anirudh Ravichander")
    seed(env, "Evergreen", artist="S. Janaki")
    seed(env, "Duet", artist="Mano")
    titles = [t["title"] for t in env.client.get(f"/tracks/{seed_t}/similar", headers=h(env)).json()]
    assert set(titles[:2]) == {"Evergreen", "Duet"}
    assert titles.index("Modern Hit") == 2


def test_romanised_tamil_title_still_counts_as_tamil_through_the_artist(env):
    seed_t, *_ = seed(env, "Vaathi Coming", artist="Anirudh Ravichander")
    seed(env, "Kutty Story", artist="Anirudh Ravichander", album="Master")
    other_lang, *_ = seed(env, "Tum Hi Ho", artist="Arijit Singh")
    titles = [t["title"] for t in env.client.get(f"/tracks/{seed_t}/similar", headers=h(env)).json()]
    assert titles[0] == "Kutty Story"
