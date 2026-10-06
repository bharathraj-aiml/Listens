import uuid

from listens_common import testing
from listens_common.config import get_settings
from listens_common.models import Album, Artist, Playlist, Track
from listens_common.storage import get_s3

from .test_upload import post


def seed(env, title="Song", artist="Band", album=None, status="ready", uploader=None, genre=None, cover=False):
    with env.sessions() as db:
        a = db.query(Artist).filter_by(name=artist).first() or Artist(name=artist)
        db.add(a)
        db.flush()
        al = None
        if album:
            al = db.query(Album).filter_by(title=album, artist_id=a.id).first() or Album(title=album, artist_id=a.id)
            db.add(al)
            db.flush()
        t = Track(artist_id=a.id, album_id=al.id if al else None, title=title, status=status, genre=genre,
                  uploader_id=uploader or env.user_id, duration_ms=1000,
                  cover_key="tracks/x.jpg" if cover else None)
        db.add(t)
        db.commit()
        return str(t.id), str(a.id), str(al.id) if al else None


def test_list_only_ready_and_mine_shows_all(env):
    seed(env, "ready one")
    seed(env, "still processing", status="processing")
    seed(env, "broken", status="failed")
    seed(env, "theirs", status="processing", uploader=env.other_id)
    titles = [t["title"] for t in env.client.get("/tracks", headers=env.headers).json()]
    assert titles == ["ready one"]
    mine = {t["title"]: t["status"] for t in env.client.get("/tracks/mine", headers=env.headers).json()}
    assert mine == {"ready one": "ready", "still processing": "processing", "broken": "failed"}


def test_get_track_visibility_and_cover_url(env):
    tid, *_ = seed(env, "p", status="processing")
    assert env.client.get(f"/tracks/{tid}", headers=env.headers).status_code == 200  # uploader sees it
    assert env.client.get(f"/tracks/{tid}", headers=env.other_headers).status_code == 404
    assert env.client.get(f"/tracks/{uuid.uuid4()}", headers=env.headers).status_code == 404
    rid, *_ = seed(env, "r", cover=True)
    t = env.client.get(f"/tracks/{rid}", headers=env.other_headers).json()
    assert t["cover_url"].startswith("/api/stream/cover/")


def test_artist_and_album_pages(env):
    t1, art, alb = seed(env, "One", "Band", "LP")
    seed(env, "Two", "Band", "LP")
    seed(env, "Hidden", "Band", "LP", status="processing")
    a = env.client.get(f"/artists/{art}", headers=env.headers).json()
    assert a["name"] == "Band" and {t["title"] for t in a["tracks"]} == {"One", "Two"}
    b = env.client.get(f"/albums/{alb}", headers=env.headers).json()
    assert b["title"] == "LP" and b["artist"]["name"] == "Band" and len(b["tracks"]) == 2
    assert env.client.get(f"/artists/{uuid.uuid4()}", headers=env.headers).status_code == 404


def test_delete_track_removes_objects_and_enforces_owner(env):
    f = testing.make_audio(env.dir / "del.mp3", title="Del")
    tid = post(env, f).json()["track"]["id"]
    assert env.client.delete(f"/tracks/{tid}", headers=env.other_headers).status_code == 403
    assert env.client.delete(f"/tracks/{tid}", headers=env.headers).status_code == 204
    assert env.client.get(f"/tracks/{tid}", headers=env.headers).status_code == 404
    s = get_settings()
    assert "Contents" not in get_s3().list_objects_v2(Bucket=s.s3_bucket_audio)


def test_search_fallback_matches_title_artist_genre_and_hides_unready(env):
    seed(env, "Midnight Drive", "Neon Owls", genre="synthwave")
    seed(env, "Sunrise", "Neon Owls")
    seed(env, "Midnight Secret", "Other", status="processing")
    with env.sessions() as db:
        db.add(Playlist(owner_id=env.user_id, name="Midnight mix", is_public=False))
        db.add(Playlist(owner_id=env.other_id, name="Midnight public", is_public=True))
        db.add(Playlist(owner_id=env.other_id, name="Midnight private", is_public=False))
        db.commit()

    def q(text):
        return env.client.get("/search", params={"q": text}, headers=env.headers).json()

    assert [t["title"] for t in q("midnight")["tracks"]] == ["Midnight Drive"]
    assert {t["title"] for t in q("neon")["tracks"]} == {"Midnight Drive", "Sunrise"}  # via artist name
    assert [a["name"] for a in q("owl")["artists"]] == ["Neon Owls"]
    assert [t["title"] for t in q("SYNTH")["tracks"]] == ["Midnight Drive"]
    assert {p["name"] for p in q("midnight")["playlists"]} == {"Midnight mix", "Midnight public"}
    assert q("100%")["tracks"] == []  # LIKE wildcards are escaped
