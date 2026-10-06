"""Short-lived signed tokens for streaming and cover URLs.

Why not S3 presigned URLs? HLS playlists reference segments by *relative* path, and a
presigned URL's signature covers one exact object, so the segments inside a playlist
would all need individual signatures (i.e. we'd have to rewrite every playlist).
Instead the signature lives in the URL *path*:

    /api/stream/hls/<token>/master.m3u8  ->  variants resolve to  /api/stream/hls/<token>/q160/seg_001.ts

so every relative reference inherits the token automatically. The stream service verifies
the HMAC + expiry, then reads the object from storage itself, so the bucket stays private.
Token = base64url(json payload) "." base64url(HMAC-SHA256(payload)).
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Literal

TokenKind = Literal["hls", "cover"]


class InvalidSignature(Exception):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, payload_b64: str) -> str:
    return _b64(hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest())


def sign_token(secret: str, kind: TokenKind, track_id: uuid.UUID, ttl_seconds: int, user_id: uuid.UUID | None = None) -> str:
    payload = {"k": kind, "t": str(track_id), "e": int(time.time()) + ttl_seconds}
    if user_id:
        payload["u"] = str(user_id)
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_mac(secret, body)}"


def verify_token(secret: str, token: str, kind: TokenKind) -> uuid.UUID:
    """Return the track id, or raise InvalidSignature (bad MAC, expired, wrong kind, malformed)."""
    try:
        body, mac = token.split(".", 1)
        # constant-time compare: don't leak how many MAC bytes matched
        if not hmac.compare_digest(mac, _mac(secret, body)):
            raise InvalidSignature("bad signature")
        payload = json.loads(_unb64(body))
        if payload["k"] != kind:
            raise InvalidSignature("wrong kind")
        if payload["e"] < time.time():
            raise InvalidSignature("expired")
        return uuid.UUID(payload["t"])
    except InvalidSignature:
        raise
    except Exception as exc:  # malformed base64/json/uuid
        raise InvalidSignature("malformed token") from exc
