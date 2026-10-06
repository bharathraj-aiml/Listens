"""FastAPI dependencies shared by services that only need to know *who* is calling."""
import uuid
from functools import lru_cache

import jwt
import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


def current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> uuid.UUID:
    """Stateless check of the access JWT (signature + expiry), no DB or network call."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    try:
        return uuid.UUID(decode_token(settings, creds.credentials, "access")["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
