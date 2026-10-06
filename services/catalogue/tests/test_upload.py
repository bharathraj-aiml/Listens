import hashlib

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
