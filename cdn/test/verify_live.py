"""Verifies the DEPLOYED CDN Worker against the REAL Backblaze buckets with one real track.

    set -a; source .env.prod; set +a; export PYTHONUTF8=1
    .venv/Scripts/python cdn/test/verify_live.py [track-uuid]

Needs DATABASE_URL (to pick a ready track) and the production STREAM_SIGNING_SECRET, taken from the
environment or, failing that, from AGENT_HANDOFF.md (NOT from .env.prod, whose value is not the one
production uses). Reads at most five small files from Backblaze, and the second pass of each is served
from Cloudflare's cache, so it costs almost nothing against the daily cap.

Expected when everything works: master/variant/segment/cover all 200, the first request of each a cache
MISS and the second a HIT, CORS present for the site's origin, and a forged link refused.
"""
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "libs" / "common"))

from sqlalchemy import select  # noqa: E402

from listens_common.db import get_sessionmaker  # noqa: E402
from listens_common.models import Track  # noqa: E402
from listens_common.signing import sign_token  # noqa: E402

CDN = os.environ.get("CDN_URL", "https://shadow-listens-cdn.shadow-listens.workers.dev")
SITE = "https://shadow-listens.shadow-listens.workers.dev"
UA = {"User-Agent": "Mozilla/5.0"}  # Cloudflare answers Python's default user agent with error 1010
results = []


def secret() -> str:
    if os.environ.get("STREAM_SIGNING_SECRET_PROD"):
        return os.environ["STREAM_SIGNING_SECRET_PROD"]
    notes = (ROOT / "AGENT_HANDOFF.md").read_text(encoding="utf-8")
    return re.search(r"STREAM_SIGNING_SECRET=([A-Za-z0-9_\-]{20,})", notes).group(1)


def fetch(url, origin=None):
    headers = dict(UA)
    if origin:
        headers["Origin"] = origin
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"   [{detail}]" if detail else ""))
    return ok


def main() -> int:
    track_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not track_id:
        with get_sessionmaker()() as db:
            t = db.scalars(select(Track).where(Track.status == "ready", Track.hls_prefix.is_not(None)).order_by(Track.created_at.desc()).limit(1)).unique().first()
            track_id, has_cover = str(t.id), bool(t.cover_key)
            print(f"track: {t.title} ({track_id})")
    else:
        has_cover = True
    tid = uuid.UUID(track_id)
    hls = sign_token(secret(), "hls", tid, 900)
    base = f"{CDN}/hls/{hls}"

    st, h, body = fetch(f"{CDN}/hls/{sign_token('wrong-secret', 'hls', tid, 900)}/master.m3u8")
    check("forged link refused", st == 403, f"{st}")

    st, h, body = fetch(f"{base}/master.m3u8", SITE)
    if st == 503:
        print("\nBackblaze is refusing reads (daily cap still exceeded?). Worker answered 503 as designed. Try again after 00:00 UTC.")
        return 2
    if not check("master playlist 200", st == 200 and b"#EXTM3U" in body, f"{st} {body[:60]!r}"):
        return 1
    check("CORS allows the site", h.get("Access-Control-Allow-Origin") == SITE, str(h.get("Access-Control-Allow-Origin")))
    variant = next(l for l in body.decode().splitlines() if l and not l.startswith("#"))

    st, _, body = fetch(f"{base}/{variant}")
    check("variant playlist 200", st == 200 and b"#EXTM3U" in body, f"{st}")
    segment = next(l for l in body.decode().splitlines() if l and not l.startswith("#"))
    seg_url = f"{base}/{variant.rsplit('/', 1)[0]}/{segment}"

    st1, h1, b1 = fetch(seg_url)
    check("segment 200 with bytes", st1 == 200 and len(b1) > 10_000, f"{st1} {len(b1)} B")
    st2, h2, b2 = fetch(seg_url)
    check("second segment read identical", st2 == 200 and b2 == b1)
    s1, s2 = h1.get("Cf-Cache-Status"), h2.get("Cf-Cache-Status")
    check("segment cached: first MISS then HIT", s2 == "HIT", f"first={s1} second={s2}")

    # a different valid link for the same file shares the cached copy
    other = fetch(f"{CDN}/hls/{sign_token(secret(), 'hls', tid, 1200, uuid.uuid4())}/{variant.rsplit('/', 1)[0]}/{segment}")
    check("another user's link gets the shared cached copy", other[0] == 200 and other[1].get("Cf-Cache-Status") == "HIT", f"{other[0]} {other[1].get('Cf-Cache-Status')}")

    if has_cover:
        cov = f"{CDN}/cover/{sign_token(secret(), 'cover', tid, 900)}"
        st, h, body = fetch(cov)
        check("cover 200 jpeg", st == 200 and h.get("Content-Type") == "image/jpeg" and body[:2] == b"\xff\xd8", f"{st}")

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
