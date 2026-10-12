from listens_common import artists, testing
from listens_common.models import Album, Artist, ArtistMeta, Follow, Track, User
from datetime import UTC, datetime


def test_slash_comma_and_semicolon_credits_are_the_same_credit():
    forms = ["Ilaiyaraaja/S. P. Balasubrahmanyam", "Ilaiyaraaja, S.P. Balasubrahmanyam", "ilaiyaraaja ; s p  balasubrahmanyam"]
    assert len({artists.credit_key(f) for f in forms}) == 1
    assert artists.canonical_credit("Ilaiyaraaja/S. P. Balasubrahmanyam") == "Ilaiyaraaja, S. P. Balasubrahmanyam"
    assert artists.canonical_credit("Madhushree;Hentry") == "Madhushree, Hentry"


def test_order_does_not_matter_for_the_key_but_people_do():
    assert artists.credit_key("A/B") == artists.credit_key("B, A")
    assert artists.credit_key("A/B") != artists.credit_key("A/C")


def test_a_name_that_contains_a_slash_stays_whole_and_blanks_are_ignored():
    assert artists.canonical_credit("AC/DC") == "AC/DC"
    assert artists.canonical_credit(" A ,, B / ") == "A, B"
    assert artists.canonical_credit("Solo Artist") == "Solo Artist"
    assert artists.canonical_credit("") == ""


def _world():
    db = testing.sqlite_sessionmaker()()
    u = User(email="a@x.io", username="a", password_hash="x", display_name="A")
    db.add(u)
    db.flush()
    return db, u


def _artist(db, u, name, tracks=0, albums=(), day=1):
    a = Artist(name=name, owner_user_id=u.id, created_at=datetime(2026, 1, day, tzinfo=UTC))
    db.add(a)
    db.flush()
    made = {}
    for title in albums:
        made[title] = Album(artist_id=a.id, title=title)
        db.add(made[title])
        db.flush()
    for i in range(tracks):
        al = made.get(albums[0]) if albums else None
        db.add(Track(artist_id=a.id, album_id=al.id if al else None, uploader_id=u.id, title=f"{name}{i}",
                     status="ready", content_sha256=f"{name}{i}"))
    db.flush()
    return a


def test_merge_folds_separator_variants_moves_everything_and_merges_same_title_albums():
    db, u = _world()
    a = _artist(db, u, "Ilaiyaraaja/S. P. Balasubrahmanyam", tracks=2, albums=("Hits",), day=1)
    b = _artist(db, u, "Ilaiyaraaja, S.P. Balasubrahmanyam", tracks=1, albums=("hits",), day=2)
    solo = _artist(db, u, "Mano", tracks=1)
    db.add(Follow(follower_id=u.id, target_type="artist", target_id=b.id))
    db.add(ArtistMeta(artist_id=b.id, mbid="m", tags={}, similar=[], fetched_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.flush()

    report = artists.merge_artists(db)
    db.flush()

    rows = {r.name: r for r in db.query(Artist).all()}
    assert set(rows) == {"Ilaiyaraaja, S. P. Balasubrahmanyam", "Mano"}
    keep = rows["Ilaiyaraaja, S. P. Balasubrahmanyam"]
    assert keep.id == a.id  # the one with the most songs survives
    assert db.query(Track).filter_by(artist_id=keep.id).count() == 3
    assert db.query(Album).filter_by(artist_id=keep.id).count() == 1  # "Hits" and "hits" became one album
    assert len({t.album_id for t in db.query(Track).filter_by(artist_id=keep.id)}) == 1
    assert db.query(Follow).filter_by(target_id=keep.id).count() == 1
    assert db.get(ArtistMeta, keep.id) is not None
    assert (report.artists_merged, report.albums_merged, report.renamed) == (1, 1, 1)
    assert db.query(Track).filter_by(artist_id=solo.id).count() == 1


def test_merge_is_idempotent_and_never_mixes_different_owners_or_people():
    db, u = _world()
    other = User(email="b@x.io", username="b", password_hash="x", display_name="B")
    db.add(other)
    db.flush()
    _artist(db, u, "A/B", tracks=1)
    _artist(db, other, "A, B", tracks=1)
    _artist(db, u, "A/C", tracks=1)
    artists.merge_artists(db)
    db.flush()
    assert db.query(Artist).count() == 3
    second = artists.merge_artists(db)
    assert (second.artists_merged, second.albums_merged, second.renamed, second.empty_removed) == (0, 0, 0, 0)


def test_artists_with_nothing_attached_are_removed_but_ones_with_a_bio_are_kept():
    db, u = _world()
    _artist(db, u, "Ghost/Row", tracks=0)
    kept = _artist(db, u, "Has, Bio", tracks=0)
    kept.bio = "Known"
    db.flush()
    report = artists.merge_artists(db)
    db.flush()
    assert [a.name for a in db.query(Artist)] == ["Has, Bio"]
    assert report.empty_removed == 1


def test_find_artist_matches_across_separators_for_the_same_owner():
    db, u = _world()
    a = _artist(db, u, "Hariharan/Sadhana Sargam", tracks=1)
    assert artists.find_artist(db, u.id, "Sadhana Sargam, Hariharan").id == a.id
    assert artists.find_artist(db, u.id, "Someone Else") is None
