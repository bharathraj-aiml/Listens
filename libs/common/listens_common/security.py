"""Password hashing and JWT helpers."""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from .config import Settings

TokenType = Literal["access", "refresh"]

# bcrypt only reads the first 72 bytes; reject longer passwords instead of silently truncating.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(settings: Settings, user_id: uuid.UUID, token_type: TokenType) -> tuple[str, str, int]:
    """Return (jwt, jti, ttl_seconds). The jti lets us revoke/rotate refresh tokens."""
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {"sub": str(user_id), "type": token_type, "jti": jti, "iat": now, "exp": now + ttl}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, int(ttl.total_seconds())


def decode_token(settings: Settings, token: str, expected: TokenType) -> dict:
    """Raises jwt.PyJWTError on bad signature/expiry/wrong type."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
