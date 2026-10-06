import re
import time

from listens_common.signing import sign_token

MASTER = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=96000\nq96/index.m3u8\n"


def put_hls(env, track_id):
    b = env.settings_.s3_bucket_audio
    env.s3.put_object(Bucket=b, Key=f"hls/{track_id}/master.m3u8", Body=MASTER)
    env.s3.put_object(Bucket=b, Key=f"hls/{track_id}/q96/index.m3u8", Body=b"#EXTM3U\nseg_000.ts\n")
    env.s3.put_object(Bucket=b, Key=f"hls/{track_id}/q96/seg_000.ts", Body=b"\x47" * 1000)
    env.s3.put_object(Bucket=b, Key=f"hls/{track_id}/secret.txt", Body=b"nope")


def get_url(env, key="ready", headers=None):
    return env.client.post(f"/tracks/{env.ids[key]}/url", headers=headers or env.headers)


def test_url_requires_auth_and_ready_track(env):
    assert env.client.post(f"/tracks/{env.ids['ready']}/url").status_code == 401
    assert get_url(env, "pending").status_code == 404
    assert env.client.post("/tracks/00000000-0000-0000-0000-000000000000/url", headers=env.headers).status_code == 404


def test_signed_url_serves_master_and_relative_segments(env):
    put_hls(env, env.ids["ready"])
    r = get_url(env)
    assert r.status_code == 200
    url, ttl = r.json()["url"], r.json()["expires_in"]
    assert re.fullmatch(r"/api/stream/hls/[\w.\-]+/master\.m3u8", url)
    assert ttl == 15 * 60  # 200 s track + 10 min slack = 800 s, raised to the 15 min floor

    base = url.removeprefix("/api/stream").rsplit("/", 1)[0]  # the gateway strips /api/stream
    m = env.client.get(base + "/master.m3u8")
    assert m.status_code == 200 and m.content == MASTER
    assert m.headers["content-type"] == "application/vnd.apple.mpegurl"
    assert "private" in m.headers["cache-control"]
    # the playlist's *relative* variant URI resolves under the same token -> works with no rewriting
    assert env.client.get(base + "/q96/index.m3u8").status_code == 200
    seg = env.client.get(base + "/q96/seg_000.ts")
    assert seg.status_code == 200 and len(seg.content) == 1000 and seg.headers["content-type"] == "video/mp2t"
    assert seg.headers["content-length"] == "1000"


def test_path_whitelist_blocks_other_objects_and_traversal(env):
    put_hls(env, env.ids["ready"])
    base = get_url(env).json()["url"].removeprefix("/api/stream").rsplit("/", 1)[0]
    # (HTTP clients normalise a literal "../" away before sending, so use the percent-encoded form
    # an attacker would actually send; Starlette decodes it back to "../" before our check.)
    for bad in ["secret.txt", "q96/other.bin", "%2e%2e/originals/x/source.mp3", "q96/%2e%2e/secret.txt",
                "q96/..%2fsecret.txt", "q9/index.m3u8", ""]:
        assert env.client.get(f"{base}/{bad}").status_code == 404, bad
    assert env.client.get(base + "/q320/seg_001.ts").status_code == 404  # whitelisted shape, missing object


def test_bad_tokens_are_forbidden(env):
    put_hls(env, env.ids["ready"])
    s, tid = env.settings_, env.ids["ready"]
    good = get_url(env).json()["url"].split("/")[4]
    cases = {
        "tampered": good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB"),
        "expired": sign_token(s.stream_signing_secret, "hls", tid, -5),
        "wrong secret": sign_token("other-secret", "hls", tid, 60),
        "cover kind": sign_token(s.stream_signing_secret, "cover", tid, 60),
        "garbage": "garbage",
    }
    for name, tok in cases.items():
        assert env.client.get(f"/hls/{tok}/master.m3u8").status_code == 403, name


def test_token_is_bound_to_its_own_track(env):
    put_hls(env, env.ids["ready"])
    # token for the "nocover" track must not unlock the "ready" track's files
    tok = sign_token(env.settings_.stream_signing_secret, "hls", env.ids["nocover"], 60)
    assert env.client.get(f"/hls/{tok}/master.m3u8").status_code == 404  # its own (empty) prefix


def test_cover_endpoint(env):
    env.s3.put_object(Bucket=env.settings_.s3_bucket_covers, Key="tracks/c.jpg", Body=b"\xff\xd8jpeg")
    tok = sign_token(env.settings_.stream_signing_secret, "cover", env.ids["ready"], 60)
    r = env.client.get(f"/cover/{tok}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8jpeg"
    no = sign_token(env.settings_.stream_signing_secret, "cover", env.ids["nocover"], 60)
    assert env.client.get(f"/cover/{no}").status_code == 404
    assert env.client.get(f"/cover/{sign_token(env.settings_.stream_signing_secret, 'hls', env.ids['ready'], 60)}").status_code == 403
    time.sleep(0)


def test_ttl_covers_track_length_but_is_clamped():
    from app.main import _ttl_for
    from listens_common.models import Track

    mk = lambda ms: Track(duration_ms=ms)  # noqa: E731
    assert _ttl_for(mk(None)) == 15 * 60
    assert _ttl_for(mk(3_600_000)) == 3600 + 600  # a 1 h mix needs a link that outlives it
    assert _ttl_for(mk(48 * 3_600_000)) == 6 * 3600  # never unbounded
