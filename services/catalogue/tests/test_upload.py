import hashlib
import uuid

from listens_common import testing
from listens_common.config import get_settings
from listens_common.models import Album, Artist, Track
from listens_common.storage import get_s3

FORM = {"license": "CC BY 4.0", "rights_confirmed": "true"}


def post(env, path, data=None, headers=None, name=None):
    with open(path, "rb") as fh:
        return env.client.post(
            "/upload", data={**FORM, **(data or {})}, files={"file": (name or path.name, fh, "audio/mpeg")},
            headers=headers or env.headers,
        )


def test_upload_reads_tags_stores_original_and_enqueues(env):
    f = testing.make_audio(env.dir / "song.mp3", title="Moon Walk", artist="The Echoes", album="Night", genre="Ambient")
    r = post(env, f)
    assert r.status_code == 201, r.text
    body = r.json()
    t = body["track"]
    assert body["duplicate"] is False
    assert (t["title"], t["artist"]["name"], t["album"]["title"], t["genre"]) == ("Moon Walk", "The Echoes", "Night", "Ambient")
    assert t["status"] == "uploaded" and t["license"] == "CC BY 4.0"

    s = get_settings()
    keys = [o["Key"] for o in get_s3().list_objects_v2(Bucket=s.s3_bucket_audio)["Contents"]]
    assert keys == [f"originals/{t['id']}/source.mp3"]
    jobs = env.redis.xrange("jobs:transcode")
    assert len(jobs) == 1 and jobs[0][1] == {"track_id": t["id"], "attempt": "0"}


def test_explicit_fields_override_tags_and_fallbacks(env):
    f = testing.make_audio(env.dir / "x.mp3", title="Tag Title", artist="Tag Artist")
    t = post(env, f, {"title": "My Title", "artist": "Me"}).json()["track"]
    assert (t["title"], t["artist"]["name"]) == ("My Title", "Me")

    bare = testing.make_audio(env.dir / "untagged_demo.flac", seconds=2)
    t = post(env, bare, name="untagged_demo.flac").json()["track"]
    assert (t["title"], t["artist"]["name"], t["album"]) == ("untagged_demo", "Unknown Artist", None)


def test_artist_and_album_are_reused_per_user(env):
    for i in range(2):
        f = testing.make_audio(env.dir / f"{i}.mp3", seconds=1 + i, title=f"T{i}", artist="Same Band", album="LP")
        assert post(env, f).status_code == 201
    with env.sessions() as db:
        assert db.query(Artist).count() == 1 and db.query(Album).count() == 1
    # another user uploading the same artist name gets their own artist row
    f = testing.make_audio(env.dir / "o.mp3", title="O", artist="same band")
    assert post(env, f, headers=env.other_headers).status_code == 201
    with env.sessions() as db:
        assert db.query(Artist).count() == 2


def test_duplicate_upload_is_detected_and_not_requeued(env):
    f = testing.make_audio(env.dir / "d.mp3", title="D")
    first = post(env, f)
    second = post(env, f)
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["track"]["id"] == first.json()["track"]["id"]
    assert env.redis.xlen("jobs:transcode") == 1
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    ex = env.client.get("/uploads/exists", params={"sha256": sha}, headers=env.headers).json()
    assert ex["exists"] is True
    assert env.client.get("/uploads/exists", params={"sha256": sha}, headers=env.other_headers).json()["exists"] is False
    assert env.client.get("/uploads/exists", params={"sha256": "0" * 64}, headers=env.headers).json()["exists"] is False


def test_validation(env):
    f = testing.make_audio(env.dir / "v.mp3")
    # rights must be confirmed
    with open(f, "rb") as fh:
        r = env.client.post("/upload", data={"license": "CC0", "rights_confirmed": "false"},
                            files={"file": ("v.mp3", fh)}, headers=env.headers)
    assert r.status_code == 400
    with open(f, "rb") as fh:  # license is required
        r = env.client.post("/upload", data={"rights_confirmed": "true"}, files={"file": ("v.mp3", fh)}, headers=env.headers)
    assert r.status_code == 422
    assert post(env, f, name="evil.exe").status_code == 415
    empty = env.dir / "empty.mp3"
    empty.write_bytes(b"")
    assert post(env, empty).status_code == 400
    assert env.redis.xlen("jobs:transcode") == 0


def test_size_limit(env, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)  # 0 MB -> any non-empty file is too big
    f = testing.make_audio(env.dir / "big.mp3")
    assert post(env, f).status_code == 413


def test_auth_required(env):
    f = testing.make_audio(env.dir / "a.mp3")
    assert env.client.post("/upload", data=FORM, files={"file": ("a.mp3", f.read_bytes())}).status_code == 401
    assert env.client.get("/tracks").status_code == 401
    assert env.client.get("/search", params={"q": "x"}).status_code == 401


def test_same_song_in_a_different_file_is_rejected_like_a_byte_duplicate(env):
    first = post(env, testing.make_audio(env.dir / "a.mp3", seconds=2, title="Moon Walk", artist="The Echoes", album="Night"))
    assert first.status_code == 201
    # different bytes (different length), same song: "moon-walk" / "THE ECHOES" differ only in case/punctuation
    again = post(env, testing.make_audio(env.dir / "b.mp3", seconds=3, title="moon-walk", artist="THE ECHOES"))
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["track"]["id"] == first.json()["track"]["id"]
    with env.sessions() as db:
        assert db.query(Track).count() == 1 and db.query(Artist).count() == 1
    assert len(env.redis.xrange("jobs:transcode")) == 1  # not re-queued
    s = get_settings()
    assert len(get_s3().list_objects_v2(Bucket=s.s3_bucket_audio)["Contents"]) == 1  # nothing extra stored


def test_untagged_files_with_the_same_filename_stem_are_not_called_duplicates(env):
    for d in ("a", "b"):
        (env.dir / d).mkdir()
    a = post(env, testing.make_audio(env.dir / "a" / "Track 01.mp3", seconds=2))
    b = post(env, testing.make_audio(env.dir / "b" / "Track 01.mp3", seconds=3))
    assert a.status_code == 201 and b.status_code == 201 and b.json()["duplicate"] is False


def test_a_song_credits_every_artist_and_each_credited_artist_page_lists_it(env):
    f = testing.make_audio(env.dir / "c.mp3", title="Duet", artist="Ilaiyaraaja/S. P. Balasubrahmanyam", album="Hits")
    t = post(env, f).json()["track"]
    assert [a["name"] for a in t["artists"]] == ["Ilaiyaraaja", "S. P. Balasubrahmanyam"]
    assert t["artist"]["name"] == "Ilaiyaraaja"  # the first credited artist is the primary one

    # a different separator and a different line-up share the same people, not new artist rows
    f2 = testing.make_audio(env.dir / "d.mp3", seconds=2, title="Solo", artist="Ilaiyaraaja, Mano", album="Hits")
    t2 = post(env, f2).json()["track"]
    with env.sessions() as db:
        assert sorted(a.name for a in db.query(Artist)) == ["Ilaiyaraaja", "Mano", "S. P. Balasubrahmanyam"]
        assert db.query(Album).count() == 1  # both songs are on one album under the primary artist
        spb = next(a for a in db.query(Artist) if a.name.startswith("S. P."))
        mano = next(a for a in db.query(Artist) if a.name == "Mano")
        for tid in (t["id"], t2["id"]):  # make the tracks listable
            db.query(Track).filter_by(id=uuid.UUID(tid)).update({"status": "ready"})
        db.commit()
    page = env.client.get(f"/artists/{spb.id}", headers=env.headers).json()
    assert [x["title"] for x in page["tracks"]] == ["Duet"]  # featured, not primary, still listed
    assert [x["title"] for x in env.client.get(f"/artists/{mano.id}", headers=env.headers).json()["tracks"]] == ["Solo"]
    assert t2["artists"][1]["name"] == "Mano"


def test_search_finds_a_song_by_any_of_its_credited_artists(env):
    f = testing.make_audio(env.dir / "s.mp3", title="Night Song", artist="Hariharan/Sadhana Sargam")
    t = post(env, f).json()["track"]
    with env.sessions() as db:
        db.query(Track).filter_by(id=uuid.UUID(t["id"])).update({"status": "ready"})
        db.commit()
    found = env.client.get("/search", params={"q": "sadhana"}, headers=env.headers).json()
    assert [x["id"] for x in found["tracks"]] == [t["id"]]
    assert [a["name"] for a in found["artists"]] == ["Sadhana Sargam"]


def test_the_same_song_credited_with_other_separators_is_a_duplicate(env):
    first = post(env, testing.make_audio(env.dir / "a.mp3", title="Same", artist="A/B")).json()
    again = post(env, testing.make_audio(env.dir / "b.mp3", seconds=2, title="Same", artist="B, A"))
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["track"]["id"] == first["track"]["id"]
