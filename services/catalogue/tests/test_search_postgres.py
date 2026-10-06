"""Full-text search against REAL Postgres (the SQLite fallback can't exercise to_tsquery/GIN).

Runs only when TEST_PG_URL is set, e.g.
  TEST_PG_URL=postgresql+psycopg2://listens@localhost:5433/listens_test pytest -k postgres
It (re)creates the schema in that database by running the real Alembic migrations.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import search
from listens_common.models import Album, Artist, Playlist, Track, User

PG_URL = os.environ.get("TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL not set")
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture(scope="module")
def db():
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        cfg = Config(str(MIGRATIONS / "alembic.ini"))
        cfg.set_main_option("script_location", str(MIGRATIONS))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        me = User(email="m@x.io", username="m", password_hash="x", display_name="M")
        you = User(email="y@x.io", username="y", password_hash="x", display_name="Y")
        session.add_all([me, you])
        session.flush()
        owls = Artist(name="Neon Owls")
        daft = Artist(name="Daft Punk")
        session.add_all([owls, daft])
        session.flush()
        album = Album(artist_id=owls.id, title="Midnight Drive")
        session.add(album)
        session.flush()
        session.add_all([
            Track(artist_id=owls.id, album_id=album.id, title="Midnight Drive", status="ready", genre="synthwave"),
            Track(artist_id=owls.id, title="Sunrise", status="ready"),
            Track(artist_id=daft.id, title="Around the World", status="ready"),
            Track(artist_id=daft.id, title="Midnight Secret", status="processing"),
            Playlist(owner_id=me.id, name="Midnight mix", is_public=False),
            Playlist(owner_id=you.id, name="Midnight public", is_public=True),
            Playlist(owner_id=you.id, name="Midnight private", is_public=False),
        ])
        session.commit()
        session.info["me"] = me.id
        yield session
    engine.dispose()


def titles(rows):
    return [t.title for t in rows]


def test_prefix_and_multi_token(db):
    r = search.search(db, "midn", db.info["me"])
    assert titles(r["tracks"]) == ["Midnight Drive"]  # 'processing' track hidden
    assert titles(search.search(db, "around the wor", db.info["me"])["tracks"]) == ["Around the World"]
    assert search.search(db, "xyzzy", db.info["me"])["tracks"] == []


def test_artist_name_finds_their_tracks_and_artist_rows(db):
    r = search.search(db, "daft", db.info["me"])
    assert [a.name for a in r["artists"]] == ["Daft Punk"]
    assert titles(r["tracks"]) == ["Around the World"]
    r = search.search(db, "neon ow", db.info["me"])
    assert {t.title for t in r["tracks"]} == {"Midnight Drive", "Sunrise"}


def test_albums_genre_and_playlist_privacy(db):
    r = search.search(db, "midnight", db.info["me"])
    assert [a.title for a in r["albums"]] == ["Midnight Drive"]
    assert {p.name for p in r["playlists"]} == {"Midnight mix", "Midnight public"}
    assert titles(search.search(db, "synth", db.info["me"])["tracks"]) == ["Midnight Drive"]


def test_hostile_input_is_harmless(db):
    for q in ["'; drop table tracks; --", "a & | ! ( ) : *", "<->", "\\", "%%%", "   "]:
        search.search(db, q, db.info["me"])  # must not raise (tsquery syntax injection)
    assert db.query(Track).count() == 4


def test_planner_uses_the_gin_indexes_at_realistic_size(db):
    """Our WHERE expressions must textually match the index expressions from migration 0002.
    On a 4-row table the planner rightly ignores any index, so load 20k rows first and let it
    choose on its own (no enable_seqscan tricks)."""
    db.execute(text("""
        INSERT INTO artists (id, name) SELECT gen_random_uuid(), 'artist ' || md5(i::text) FROM generate_series(1, 20000) i;
        INSERT INTO albums (id, artist_id, title) SELECT gen_random_uuid(), (SELECT id FROM artists LIMIT 1), 'album ' || md5(i::text) FROM generate_series(1, 20000) i;
        INSERT INTO tracks (id, artist_id, title, status) SELECT gen_random_uuid(), (SELECT id FROM artists LIMIT 1), 'song ' || md5(i::text), 'ready' FROM generate_series(1, 20000) i;
        INSERT INTO playlists (id, owner_id, name, is_public) SELECT gen_random_uuid(), (SELECT id FROM users LIMIT 1), 'list ' || md5(i::text), true FROM generate_series(1, 20000) i;
    """))
    db.commit()
    db.execute(text("ANALYZE"))
    for sql, index in [
        (search.PG_TRACKS, "ix_fts_tracks"), (search.PG_ARTISTS, "ix_fts_artists"),
        (search.PG_ALBUMS, "ix_fts_albums"), (search.PG_PLAYLISTS, "ix_fts_playlists"),
    ]:
        plan = "\n".join(db.scalars(text("EXPLAIN " + sql), {"q": "mid:*", "n": 5, "uid": db.info["me"]}))
        assert index in plan, f"{index} not used:\n{plan}"
    # and the real thing still works on the larger table
    assert [t.title for t in search.search(db, "midnight", db.info["me"])["tracks"]] == ["Midnight Drive"]
