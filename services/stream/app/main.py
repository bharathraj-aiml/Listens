"""Stream service: issues short-lived signed URLs and serves HLS/cover bytes from private storage.

Flow:  POST /tracks/{id}/url  (JWT)  ->  {"url": "/api/stream/hls/<token>/master.m3u8"}
       GET  /hls/<token>/master.m3u8, /hls/<token>/q160/seg_003.ts, ...  (token = the credential)
The token embeds track id + expiry, signed with HMAC (see listens_common.signing).
"""
import logging
import re
import uuid

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.db import get_db
from listens_common.models import Track
from listens_common.signing import InvalidSignature, sign_token, verify_token
from listens_common.storage import get_s3
from listens_common.web import current_user_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("stream")

app = FastAPI(title="Shadow Listens - Stream", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Range"],
)

# Whitelist, not blacklist: only the exact file shapes the worker produces can be requested,
# which also rules out path traversal ("../") by construction.
HLS_PATH = re.compile(r"^(master\.m3u8|q\d{2,3}/(index\.m3u8|seg_\d{3,5}\.ts))$")
CONTENT_TYPES = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}
MIN_TTL, MAX_TTL, TTL_SLACK = 15 * 60, 6 * 3600, 10 * 60


class StreamUrlOut(BaseModel):
    url: str
    expires_in: int


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _ttl_for(track: Track) -> int:
    """Playback fetches segments progressively, so the URL must outlive the track.
    Duration + slack, clamped; still 'short-lived' (minutes), never a permanent link."""
    seconds = (track.duration_ms or 0) // 1000 + TTL_SLACK
    return max(MIN_TTL, min(seconds, MAX_TTL))


@app.post("/tracks/{track_id}/url", response_model=StreamUrlOut)
def stream_url(
    track_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamUrlOut:
    track = db.get(Track, track_id)
    if track is None or track.status != "ready":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not available")
    ttl = _ttl_for(track)
    token = sign_token(settings.stream_signing_secret, "hls", track.id, ttl, user_id)
    return StreamUrlOut(url=f"{settings.stream_public_prefix}/hls/{token}/master.m3u8", expires_in=ttl)


def _verify(settings: Settings, token: str, kind: str) -> uuid.UUID:
    try:
        return verify_token(settings.stream_signing_secret, token, kind)
    except InvalidSignature:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired link") from None


def _stream_object(bucket: str, key: str, content_type: str) -> StreamingResponse:
    try:
        obj = get_s3().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
        raise
    headers = {
        "Content-Length": str(obj["ContentLength"]),
        # The token in the URL is the credential, so caches must stay per-user ("private").
        "Cache-Control": "private, max-age=3600",
    }
    return StreamingResponse(obj["Body"].iter_chunks(64 * 1024), media_type=content_type, headers=headers)


@app.get("/hls/{token}/{path:path}")
def hls(token: str, path: str, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    track_id = _verify(settings, token, "hls")
    if not HLS_PATH.match(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    ext = "." + path.rsplit(".", 1)[1]
    return _stream_object(settings.s3_bucket_audio, f"hls/{track_id}/{path}", CONTENT_TYPES[ext])


@app.get("/cover/{token}")
def cover(token: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> StreamingResponse:
    track_id = _verify(settings, token, "cover")
    track = db.get(Track, track_id)
    if track is None or not track.cover_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _stream_object(settings.s3_bucket_covers, track.cover_key, "image/jpeg")
