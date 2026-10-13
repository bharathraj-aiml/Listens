from listens_common import artists, testing
from listens_common.models import Album, Artist, ArtistMeta, Follow, Track, TrackArtist, User
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


def test_ensure_artists_makes_one_artist_per_person_and_reuses_them():
    db, u = _world()
    first = artists.ensure_artists(db, u.id, "Yuvan Shankar Raja/Na.Muthukumar")
    again = artists.ensure_artists(db, u.id, "Na.Muthukumar, Yuvanshankar Raja, Hariharan")
    assert [a.name for a in first] == ["Yuvan Shankar Raja", "Na.Muthukumar"]
    assert [a.name for a in again] == ["Na.Muthukumar", "Yuvan Shankar Raja", "Hariharan"]  # spelling variants are the same person
    assert again[0].id == first[1].id and again[1].id == first[0].id
    assert db.query(Artist).count() == 3
    assert [a.name for a in artists.ensure_artists(db, u.id, "")] == ["Unknown Artist"]


def test_set_track_artists_orders_credits_and_sets_the_primary():
    db, u = _world()
    a, b, c = (artists.ensure_artists(db, u.id, n)[0] for n in ("A", "B", "C"))
    t = _artist(db, u, "Placeholder", tracks=1)
    track = db.query(Track).first()
    artists.set_track_artists(db, track, [b, a, b, c])  # repeats are ignored
    assert [x.name for x in track.artists] == ["B", "A", "C"]
    assert track.artist_id == b.id
    assert artists.credit_of(track) == "B, A, C"
    artists.set_track_artists(db, track, [c])
    assert [x.name for x in track.artists] == ["C"] and track.artist_id == c.id


def test_split_credits_turns_credit_rows_into_people_and_keeps_every_track_reachable():
    db, u = _world()
    x = _artist(db, u, "Harris Jayaraj, Karthik", tracks=2, albums=("Film",), day=1)
    y = _artist(db, u, "Harris Jayaraj/Chinmayi", tracks=1, albums=("film",), day=2)
    solo = _artist(db, u, "Mano", tracks=1)
    db.add(Follow(follower_id=u.id, target_type="artist", target_id=x.id))
    db.flush()

    report = artists.split_credits(db)
    db.flush()

    assert sorted(a.name for a in db.query(Artist)) == ["Chinmayi", "Harris Jayaraj", "Karthik", "Mano"]
    harris = db.query(Artist).filter_by(name="Harris Jayaraj").one()
    assert db.query(Album).count() == 1 and db.query(Album).one().artist_id == harris.id  # both "Film" albums merged
    assert len({t.album_id for t in db.query(Track).filter(Track.artist_id == harris.id)}) == 1
    credited = {a.name: sorted(t.title for t in db.query(Track).join(TrackArtist, TrackArtist.track_id == Track.id).filter(TrackArtist.artist_id == a.id)) for a in db.query(Artist)}
    assert len(credited["Harris Jayaraj"]) == 3 and len(credited["Karthik"]) == 2 and len(credited["Chinmayi"]) == 1
    assert credited["Mano"] == [f"Mano{i}" for i in range(1)]
    assert all(t.artists for t in db.query(Track))  # every track has link rows, single-artist ones too
    assert db.query(Follow).filter_by(target_id=harris.id).count() == 1  # the follow moved to the first person
    assert (report.credits_split, report.albums_merged) == (2, 1)

    again = artists.split_credits(db)
    assert (again.credits_split, again.tracks_linked, again.albums_merged, again.people_created) == (0, 0, 0, 0)
    assert solo.id  # untouched row


def test_known_misspellings_are_the_same_person():
    for wrong, right in [("Harish Ragavendra", "Harish Raghavendra"), ("S.P.Balasubramniam", "S. P. Balasubrahmanyam"), ("Sadhna Sargam", "Sadhana Sargam")]:
        assert artists.person_name(wrong) == right == artists.person_name(right)


def test_a_misspelt_artist_merges_into_the_right_spelling_and_keeps_every_credit_link():
    db, u = _world()
    right = _artist(db, u, "Harish Raghavendra", tracks=2)
    wrong = _artist(db, u, "Harish Ragavendra", tracks=1, day=2)
    other = _artist(db, u, "Mano", tracks=1)
    t_wrong = db.query(Track).filter_by(artist_id=wrong.id).one()
    # a song credited to BOTH spellings and to Mano: the link rows must collapse to one, not collide
    artists.set_track_artists(db, t_wrong, [wrong, other])
    for t in db.query(Track).filter_by(artist_id=right.id):
        artists.set_track_artists(db, t, [right])
    artists.set_track_artists(db, db.query(Track).filter_by(artist_id=other.id).one(), [other])
    db.flush()

    artists.merge_artists(db)
    db.flush()

    assert sorted(a.name for a in db.query(Artist)) == ["Harish Raghavendra", "Mano"]
    for t in db.query(Track):
        db.refresh(t)
    names = {t.title: [a.name for a in t.artists] for t in db.query(Track)}
    assert names[t_wrong.title] == ["Harish Raghavendra", "Mano"]
    assert all(t.artists for t in db.query(Track))  # nobody lost their credit


def test_merge_never_removes_an_artist_that_is_only_credited_never_first():
    db, u = _world()
    lead = _artist(db, u, "Lead", tracks=1)
    guest = artists.ensure_artists(db, u.id, "Guest")[0]  # no song has Guest as its primary artist
    artists.set_track_artists(db, db.query(Track).one(), [lead, guest])
    db.flush()
    report = artists.merge_artists(db)
    db.flush()
    assert sorted(a.name for a in db.query(Artist)) == ["Guest", "Lead"] and report.empty_removed == 0
