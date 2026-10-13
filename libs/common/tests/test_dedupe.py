from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from listens_common import dedupe, testing
from listens_common.models import Album, Artist, Like, Playlist, PlaylistTrack, Track, User

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def make_world():
    Session = testing.sqlite_sessionmaker()
    db = Session()
    u = User(email="a@x.io", username="a", password_hash="x", display_name="A")
    other = User(email="b@x.io", username="b", password_hash="x", display_name="B")
    db.add_all([u, other])
    db.flush()
    return db, u, other


def add_track(db, user, title="Moon Walk", artist="The Echoes", album=None, *, kbps=192, ms=240_000,
              status="ready", age_days=0):
    a = db.query(Artist).filter_by(name=artist, owner_user_id=user.id).first() or Artist(name=artist, owner_user_id=user.id)
    db.add(a)
    db.flush()
    al = None
    if album:
        al = db.query(Album).filter_by(title=album, artist_id=a.id).first() or Album(title=album, artist_id=a.id)
        db.add(al)
        db.flush()
    t = Track(artist_id=a.id, album_id=al.id if al else None, uploader_id=user.id, title=title, status=status,
              duration_ms=ms, source_bitrate_kbps=kbps, created_at=T0 + timedelta(days=age_days),
              content_sha256=f"{title}{artist}{kbps}{age_days}{ms}")
    db.add(t)
    db.commit()
    return t


def test_norm_ignores_case_punctuation_and_spacing_but_not_letters_or_marks():
    assert dedupe.norm("  Moon-Walk!! ") == dedupe.norm("moon   walk") == "moon walk"
    assert dedupe.norm("Café") == dedupe.norm("CAFÉ")
    # Tamil vowel signs are combining marks: dropping them would make different words collide
    assert dedupe.norm("கலை") != dedupe.norm("கல")


def test_same_song_is_found_across_case_punctuation_and_a_missing_album():
    db, u, _ = make_world()
    existing = add_track(db, u, album="Night")
    found = dedupe.find_duplicates(db, u.id, "moon walk!", "the echoes", None)
    assert [t.id for t in found] == [existing.id]
    assert dedupe.find_duplicates(db, u.id, "Moon Walk", "The Echoes", "Night")
    assert not dedupe.find_duplicates(db, u.id, "Moon Walk", "The Echoes", "A Different Album")


def test_different_titles_artists_users_and_failed_tracks_are_not_duplicates():
    db, u, other = make_world()
    add_track(db, u)
    add_track(db, u, title="Moon Walk (Live)", artist="The Echoes", kbps=128)
    assert not dedupe.find_duplicates(db, u.id, "Moon Walk (Remix)", "The Echoes")
    assert not dedupe.find_duplicates(db, u.id, "Moon Walk", "Other Band")
    assert not dedupe.find_duplicates(db, other.id, "Moon Walk", "The Echoes")  # someone else's library
    failed = add_track(db, u, title="Broken", status="failed")
    assert not dedupe.find_duplicates(db, u.id, "Broken", "The Echoes")
    assert failed.status == "failed"


def test_untagged_unknown_artist_files_are_never_judged_duplicates():
    db, u, _ = make_world()
    add_track(db, u, title="Track 01", artist="Unknown Artist")
    assert not dedupe.find_duplicates(db, u.id, "Track 01", "Unknown Artist")


def test_duration_must_be_within_tolerance_when_given():
    db, u, _ = make_world()
    add_track(db, u, ms=240_000)
    assert dedupe.find_duplicates(db, u.id, "Moon Walk", "The Echoes", duration_ms=242_000)
    assert not dedupe.find_duplicates(db, u.id, "Moon Walk", "The Echoes", duration_ms=250_000)


def test_keeper_is_highest_bitrate_then_oldest():
    db, u, _ = make_world()
    low = add_track(db, u, kbps=128, age_days=0)
    high_new = add_track(db, u, kbps=320, age_days=5, ms=240_500)
    high_old = add_track(db, u, kbps=320, age_days=1, ms=240_200)
    assert dedupe.pick_keeper([low, high_new, high_old]).id == high_old.id


def test_resolve_keeps_best_copy_deletes_rest_and_moves_likes_and_playlists():
    db, u, other = make_world()
    low = add_track(db, u, kbps=128, age_days=0)
    best = add_track(db, u, kbps=320, age_days=3, ms=240_400)
    pl = Playlist(owner_id=u.id, name="p")
    db.add(pl)
    db.flush()
    db.add_all([Like(user_id=u.id, track_id=low.id), Like(user_id=other.id, track_id=low.id), Like(user_id=other.id, track_id=best.id),
                PlaylistTrack(playlist_id=pl.id, track_id=low.id, position=0, added_by=u.id)])
    db.commit()
    low_id, best_id = low.id, best.id

    s3 = MagicMock()
    settings = SimpleNamespace(s3_bucket_audio="audio", s3_bucket_covers="covers")
    removed = dedupe.resolve_duplicates(db, s3, settings, best_id)

    assert removed == [low_id]
    assert db.get(Track, low_id) is None and db.get(Track, best_id) is not None
    assert {(l.user_id, l.track_id) for l in db.query(Like)} == {(u.id, best_id), (other.id, best_id)}  # moved, no double like
    assert db.query(PlaylistTrack).one().track_id == best_id
    s3.get_paginator.assert_called()  # its originals/ and hls/ prefixes were cleaned


def test_resolve_on_a_unique_song_changes_nothing():
    db, u, _ = make_world()
    t = add_track(db, u)
    assert dedupe.resolve_duplicates(db, MagicMock(), SimpleNamespace(), t.id) == []
    assert db.get(Track, t.id) is not None


# ------------------------------------------------- spelling variants of the same song

def _song(title, people=(1,), album=None, ms=300_000):
    return dedupe.SongInfo(title, set(people), album, ms)


def test_spelling_variants_of_a_title_are_the_same_song():
    assert dedupe.likely_same_song(_song("En Veettu Thottathil"), _song("En Veetu Thotathil", ms=301_000))
    assert dedupe.likely_same_song(_song("Aaruyire"), _song('Aaruyire (From "Guru")'))
    assert dedupe.likely_same_song(_song('Kurukku Siruthvalea - From "Mudhalvan"'), _song("Kurukku Chiruthavale"))
    assert not dedupe.likely_same_song(_song("Moon Walk"), _song("Sun Rise"))


def test_a_slowed_live_or_remixed_version_is_not_a_duplicate():
    assert not dedupe.likely_same_song(_song("Jumpstyle"), _song("Jumpstyle - Slowed"))
    assert not dedupe.likely_same_song(_song("Ku Lo Sa"), _song("KU LO SA - A COLORS SHOW"))
    assert dedupe.likely_same_song(_song("Song (Remix)"), _song("Song - Remix"))  # the same version on both sides


def test_a_very_different_length_or_an_unrelated_artist_is_not_a_duplicate():
    assert not dedupe.likely_same_song(_song("Same Name", ms=240_000), _song("Same Name", ms=330_000))
    assert not dedupe.likely_same_song(_song("Same Name", people=(1,), album="A"), _song("Same Name", people=(2,), album="B", ms=240_000 + 9_000))


def test_strict_mode_needs_a_known_close_length_and_a_shared_artist():
    a = _song("Same Name", ms=240_000)
    assert dedupe.likely_same_song(a, _song("Same Name", ms=243_000), strict=True)
    assert not dedupe.likely_same_song(a, _song("Same Name", ms=250_000), strict=True)  # lenient would accept 10 s
    assert dedupe.likely_same_song(a, _song("Same Name", ms=250_000))
    assert not dedupe.likely_same_song(a, _song("Same Name", ms=None), strict=True)
    assert not dedupe.likely_same_song(a, _song("Same Name", people=(9,), ms=240_500), strict=True)


def test_similar_groups_links_chains_and_ignores_singletons():
    songs = [_song("Mazhai Kuruvi"), _song("Mazhai Kuruvi", ms=300_900), _song("Totally Other", people=(5,)), _song("Mazhai Kuruvi (From X)", ms=301_500)]
    assert [sorted(g) for g in dedupe.similar_groups(songs)] == [[0, 1, 3]]


def test_a_new_ready_track_removes_its_spelling_variant_and_play_history_follows():
    from listens_common.models import PlayEvent

    db, u, _ = make_world()
    keep = add_track(db, u, title="Veettu Thottathil", artist="Rahman", kbps=192, ms=245_000)
    twin = add_track(db, u, title="Veetu Thotathil", artist="Rahman", kbps=128, ms=244_000, age_days=1)
    db.add(PlayEvent(user_id=u.id, track_id=twin.id, event_type="play_end", ms_played=1000, position_ms=0, occurred_at=T0))
    db.commit()
    group = dedupe.duplicate_group(db, twin)
    assert {t.id for t in group} == {keep.id, twin.id}
    assert dedupe.pick_keeper(group).id == keep.id
    s3, settings = MagicMock(), SimpleNamespace(s3_bucket_audio="a", s3_bucket_covers="c")
    from unittest.mock import patch

    with patch("listens_common.storage.delete_prefix"):
        dedupe.remove_track(db, s3, settings, twin, keep=keep)
    assert db.query(PlayEvent).one().track_id == keep.id


# ------------------------------------------------------- the pre-upload checking layer

def _check(db, u, **kw):
    kw.setdefault("title", "Moon Walk")
    kw.setdefault("credit", "The Echoes")
    return dedupe.check_duplicate(db, u.id, **kw)


def test_check_duplicate_tiers_identical_bytes_exact_and_variant():
    db, u, other = make_world()
    t = add_track(db, u, title="Veettu Thottathil", artist="Rahman", album="Gentleman", ms=245_000)
    t.content_sha256 = "abc123"
    db.commit()
    assert _check(db, u, title="Different", credit="Someone", sha256="abc123").reason.startswith("this exact file")
    assert _check(db, u, title="veettu thottathil!", credit="rahman").reason.startswith("same title and artist")
    variant = _check(db, u, title="Veetu Thotathil", credit="Rahman, Vairamuthu", album="Gentleman (Original Motion Picture Soundtrack)", duration_ms=244_000)
    assert variant is not None and variant.track.id == t.id and "spelling or credit" in variant.reason
    assert _check(db, other, title="Veetu Thotathil", credit="Rahman") is None  # another user's library is irrelevant


def test_check_duplicate_lets_genuinely_different_songs_and_versions_through():
    db, u, _ = make_world()
    add_track(db, u, title="Jumpstyle", artist="Twxny", ms=120_000)
    assert _check(db, u, title="Jumpstyle - Slowed", credit="Twxny", duration_ms=121_000) is None  # a different version
    assert _check(db, u, title="Jumpstyle", credit="Twxny", duration_ms=300_000) is None  # a very different length (a long mix)
    assert _check(db, u, title="Jumpstyle", credit="Twxny", duration_ms=121_000) is not None  # the same length is a repeat
    assert _check(db, u, title="Another Song", credit="Twxny", duration_ms=120_000) is None
    assert _check(db, u, title="Jumpstyle", credit="Unknown Artist") is None  # untagged: only bytes are compared


def test_find_ready_twin_only_returns_processed_songs():
    db, u, _ = make_world()
    ready = add_track(db, u, title="Mazhai Kuruvi", artist="Rahman", status="ready")
    waiting = add_track(db, u, title="Mazhai Kuruvi", artist="Rahman, Vairamuthu", status="uploaded", ms=348_000)
    assert dedupe.find_ready_twin(db, waiting).id == ready.id
    assert dedupe.find_ready_twin(db, ready) is None  # the only processed copy is never a repeat of a waiting one
