"""Runs the CDN Worker locally (wrangler dev / workerd) against a mock S3 server and checks it end to end.

    .venv/Scripts/python cdn/test/e2e_local.py

Covers what the unit tests cannot: routing, signed-request reads from S3, headers, CORS, error mapping,
and whether a second request is served from cache (the object is deleted from S3 between the two reads,
so a 200 on the second read can only have come from the cache). Needs Node, and the project venv (moto).
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "libs" / "common"))

import boto3  # noqa: E402
from moto.server import ThreadedMotoServer  # noqa: E402

from listens_common.signing import sign_token  # noqa: E402

SECRET = "e2e-signing-secret"
ALLOWED = "https://site.example"
TRACK = uuid.uuid4()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"   [{detail}]" if detail and not ok else ""))


def main() -> int:
    s3_port, cdn_port = free_port(), free_port()
    moto = ThreadedMotoServer(ip_address="127.0.0.1", port=s3_port, verbose=False)
    moto.start()
    endpoint = f"http://127.0.0.1:{s3_port}"
    s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id="k", aws_secret_access_key="s", region_name="us-east-1")
    for b in ("e2e-audio", "e2e-covers"):
        s3.create_bucket(Bucket=b)
    segment = os.urandom(50_000)
    cover = b"\xff\xd8\xff" + os.urandom(2_000)
    base = f"hls/{TRACK}"
    s3.put_object(Bucket="e2e-audio", Key=f"{base}/master.m3u8", Body=b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=160000\nq160/index.m3u8\n")
    s3.put_object(Bucket="e2e-audio", Key=f"{base}/q160/index.m3u8", Body=b"#EXTM3U\nseg_000.ts\n")
    s3.put_object(Bucket="e2e-audio", Key=f"{base}/q160/seg_000.ts", Body=segment)
    s3.put_object(Bucket="e2e-covers", Key=f"tracks/{TRACK}.jpg", Body=cover)

    env = {**os.environ, "NO_COLOR": "1", "WRANGLER_SEND_METRICS": "false"}
    log_path = ROOT / "cdn" / ".wrangler" / "e2e.log"
    log_path.parent.mkdir(exist_ok=True)
    log = open(log_path, "w")
    dev = subprocess.Popen(
        ["npx.cmd" if os.name == "nt" else "npx", "--yes", "wrangler", "dev", "--port", str(cdn_port), "--ip", "127.0.0.1", "--local",
         "--var", f"STREAM_SIGNING_SECRET:{SECRET}", "--var", "S3_ACCESS_KEY:k", "--var", "S3_SECRET_KEY:s",
         "--var", f"S3_ENDPOINT_URL:{endpoint}", "--var", "S3_REGION:us-east-1",
         "--var", "S3_BUCKET_AUDIO:e2e-audio", "--var", "S3_BUCKET_COVERS:e2e-covers", "--var", f"ALLOWED_ORIGINS:{ALLOWED}"],
        cwd=ROOT / "cdn", env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
    )
    cdn = f"http://127.0.0.1:{cdn_port}"
    try:
        for _ in range(60):
            try:
                if get(f"{cdn}/health")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print("worker never became ready; see", log_path)
            return 1

        hls = sign_token(SECRET, "hls", TRACK, 600)
        cov = sign_token(SECRET, "cover", TRACK, 600)

        st, h, body = get(f"{cdn}/hls/{hls}/master.m3u8", {"Origin": ALLOWED})
        check("master playlist served", st == 200 and b"q160/index.m3u8" in body, f"{st}")
        check("playlist content type", h.get("Content-Type", "").startswith("application/vnd.apple.mpegurl"), str(h))
        check("allowed origin gets CORS", h.get("Access-Control-Allow-Origin") == ALLOWED, str(h))
        st, h, _ = get(f"{cdn}/hls/{hls}/master.m3u8", {"Origin": "https://evil.example"})
        check("other origin gets no CORS header", "Access-Control-Allow-Origin" not in h)

        st, h, body = get(f"{cdn}/hls/{hls}/q160/seg_000.ts")
        check("segment bytes identical to storage", st == 200 and body == segment, f"{st} {len(body)}")
        check("segment cached for a year", "immutable" in h.get("Cache-Control", ""), h.get("Cache-Control", ""))
        check("segment content type", h.get("Content-Type") == "video/mp2t", h.get("Content-Type", ""))

        st, h, body = get(f"{cdn}/cover/{cov}")
        check("cover served as jpeg", st == 200 and body == cover and h.get("Content-Type") == "image/jpeg", f"{st}")

        st, h, _ = get(f"{cdn}/hls/{hls}/master.m3u8", {"Origin": ALLOWED, "Access-Control-Request-Method": "GET"}, method="OPTIONS")
        check("preflight answered", st == 204 and h.get("Access-Control-Allow-Origin") == ALLOWED, f"{st}")

        # security: nothing is served without a valid link, and the cache is never consulted first
        expired = sign_token(SECRET, "hls", TRACK, -10)
        forged = sign_token("some-other-secret", "hls", TRACK, 600)
        check("no token -> 404", get(f"{cdn}/hls/x/master.m3u8")[0] == 403)
        check("expired link -> 403", get(f"{cdn}/hls/{expired}/master.m3u8")[0] == 403)
        check("forged link -> 403", get(f"{cdn}/hls/{forged}/master.m3u8")[0] == 403)
        check("cover link cannot open audio", get(f"{cdn}/hls/{cov}/master.m3u8")[0] == 403)
        check("path outside the whitelist -> 404", get(f"{cdn}/hls/{hls}/..%2Fsecret.txt")[0] == 404)
        check("unknown file -> 404", get(f"{cdn}/hls/{hls}/q160/seg_999.ts")[0] == 404)
        check("POST refused", get(f"{cdn}/hls/{hls}/master.m3u8", method="POST")[0] == 405)

        # caching: remove the object from storage; a cache hit still answers, with a different valid token
        s3.delete_object(Bucket="e2e-audio", Key=f"{base}/q160/seg_000.ts")
        other_token = sign_token(SECRET, "hls", TRACK, 900, uuid.uuid4())
        st, _, body = get(f"{cdn}/hls/{other_token}/q160/seg_000.ts")
        check("second read comes from cache even after storage lost it (different token, shared entry)", st == 200 and body == segment, f"{st}")
        st, _, _ = get(f"{cdn}/hls/{expired}/q160/seg_000.ts")
        check("...but an expired link still gets nothing from the cache", st == 403, f"{st}")
    finally:
        dev.terminate()
        try:
            dev.wait(timeout=10)
        except Exception:
            dev.kill()
        moto.stop()

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
