from datetime import UTC, datetime

from listens_common import albums, artists, testing
from listens_common.models import Album, Artist, Track, User


def test_store_boilerplate_is_removed_but_real_information_stays():
    clean = albums.clean_album_title
    assert clean("Guru (Original Motion Picture Soundtrack)") == "Guru"
    assert clean("Jilla (Original Music Picture Soundtrack)") == "Jilla"  # a misspelt suffix too
    assert clean("Jodhaa Akbar (Tamil) [Original Motion Picture Soundtrack]") == "Jodhaa Akbar (Tamil)"
    assert clean("Paiya (Deluxe Edition) [Original Motion Picture Soundtrack]") == "Paiya"
    assert clean('Mogam (From "K.G.F. Chapter 1") - Single') == 'Mogam (From "K.G.F. Chapter 1")'
    assert clean("Best Friend (feat. Doja Cat) [Remix EP] [Extended Edition]") == "Best Friend (feat. Doja Cat)"
    assert clean("Gentleman Original Motion Picture Soundtrack") == "Gentleman"
    # kept: the film a single is from, a version, a real subtitle
    assert clean('Adheeraa (From "Cobra")') == 'Adheeraa (From "Cobra")'
    assert clean("Love Me Back (Fayahh Beat) [Slowed + Reverb]") == "Love Me Back (Fayahh Beat) [Slowed + Reverb]"
    assert clean("Naan Unnai Ninaithen - Tamil Romantic Music,Vol. 2") == "Naan Unnai Ninaithen - Tamil Romantic Music,Vol. 2"
    assert clean("(Original Motion Picture Soundtrack)") == "(Original Motion Picture Soundtrack)"  # never empty
    assert clean("") == ""


def _world():
    db = testing.sqlite_sessionmaker()()
    u = User(email="a@x.io", username="a", password_hash="x", display_name="A")
    db.add(u)
    db.flush()
    return db, u


def _song(db, u, title, credit, album, day=1):
    people = artists.ensure_artists(db, u.id, credit)
    al = albums.find_or_create_album(db, people, album)
    t = Track(artist_id=people[0].id, album_id=al.id, uploader_id=u.id, title=title, status="ready", content_sha256=title + credit)
    db.add(t)
    db.flush()
    artists.set_track_artists(db, t, people)
    return t


def test_uploads_reuse_an_album_across_suffix_spellings_and_first_listed_singers():
    db, u = _world()
    a = _song(db, u, "S1", "Rahman, Hariharan", "Guru (Original Motion Picture Soundtrack)")
    b = _song(db, u, "S2", "Chinmayi, Rahman", "Guru")  # a different first-listed singer, same film and composer
    c = _song(db, u, "S3", "Someone Else", "Guru")  # an unrelated artist with the same title: a different album
    assert a.album_id == b.album_id != c.album_id
    assert sorted(x.title for x in db.query(Album)) == ["Guru", "Guru"]


def test_existing_albums_are_cleaned_and_folded_together():
    db, u = _world()
    r = artists.ensure_artists(db, u.id, "Rahman")[0]
    for i, title in enumerate(["Guru (Original Motion Picture Soundtrack)", "Guru [Original Motion Picture Soundtrack]", "Guru"]):
        al = Album(artist_id=r.id, title=title, created_at=datetime(2026, 1, 1 + i, tzinfo=UTC))
        db.add(al)
        db.flush()
        t = Track(artist_id=r.id, album_id=al.id, uploader_id=u.id, title=f"T{i}", status="ready", content_sha256=f"h{i}")
        db.add(t)
        db.flush()
        artists.set_track_artists(db, t, [r])
    other = Album(artist_id=r.id, title="Roja (Original Motion Picture Soundtrack)")
    db.add(other)
    db.flush()

    report = albums.normalize_albums(db)
    db.flush()

    assert sorted(a.title for a in db.query(Album)) == ["Guru", "Roja"]
    assert len({t.album_id for t in db.query(Track)}) == 1  # the three Guru albums are one
    assert (report.renamed, report.merged) == (3, 2)
    assert albums.normalize_albums(db).merged == 0  # idempotent


def test_unrelated_artists_with_the_same_album_title_are_not_merged():
    db, u = _world()
    for name in ("Alpha", "Beta"):
        p = artists.ensure_artists(db, u.id, name)[0]
        al = Album(artist_id=p.id, title="Greatest Hits")
        db.add(al)
        db.flush()
        t = Track(artist_id=p.id, album_id=al.id, uploader_id=u.id, title=name, status="ready", content_sha256=name)
        db.add(t)
        db.flush()
        artists.set_track_artists(db, t, [p])
    assert albums.normalize_albums(db).merged == 0 and db.query(Album).count() == 2
