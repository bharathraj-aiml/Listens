import logging
import uuid

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from listens_common.config import Settings, get_settings
from listens_common.models import User
from listens_common.security import create_token, decode_token, hash_password, verify_password

from .deps import current_user, get_db, get_redis
from .schemas import LoginIn, ProfileUpdate, RefreshIn, RegisterIn, TokenPair, UserOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("auth")

app = FastAPI(title="Shadow Listens - Auth", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,  # tokens travel in the Authorization header, not cookies
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Refresh-token design: refresh JWTs are stateful. Each carries a `jti`; the server keeps
# `refresh:<jti> -> user_id` in Redis with a TTL equal to the token lifetime.
#  - refresh  : delete the old jti, issue a new pair (rotation). A replayed old token
#               finds nothing in Redis and is rejected.
#  - logout   : delete the jti -> token is dead immediately, even though the JWT is unexpired.
# Access tokens stay stateless and short-lived (15 min) so other services can verify them
# with just the shared secret, no network call.
_REFRESH_KEY = "refresh:{jti}"


def _issue_pair(settings: Settings, r: Redis, user_id: uuid.UUID) -> TokenPair:
    access, _, access_ttl = create_token(settings, user_id, "access")
    refresh, jti, refresh_ttl = create_token(settings, user_id, "refresh")
    r.set(_REFRESH_KEY.format(jti=jti), str(user_id), ex=refresh_ttl)
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=access_ttl)


def _bad_refresh() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> User:
    email = body.email.lower()
    taken = db.scalar(
        select(User).where(or_(func.lower(User.email) == email, func.lower(User.username) == body.username.lower()))
    )
    if taken:
        field = "Email" if taken.email.lower() == email else "Username"
        raise HTTPException(status.HTTP_409_CONFLICT, f"{field} already in use")
    user = User(
        email=email,
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already in use") from None
    log.info("registered user %s", user.id)
    return user


@app.post("/login", response_model=TokenPair)
def login(
    body: LoginIn,
    db: Session = Depends(get_db),
    r: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    ident = body.identifier.strip().lower()
    user = db.scalar(select(User).where(or_(func.lower(User.email) == ident, func.lower(User.username) == ident)))
    # Same error for unknown user and wrong password: don't reveal which accounts exist.
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _issue_pair(settings, r, user.id)


@app.post("/refresh", response_model=TokenPair)
def refresh(
    body: RefreshIn,
    db: Session = Depends(get_db),
    r: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    try:
        payload = decode_token(settings, body.refresh_token, "refresh")
        user_id = uuid.UUID(payload["sub"])
        jti = payload["jti"]
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _bad_refresh() from None
    # GETDEL is atomic: of two concurrent refreshes with the same token, only one wins.
    if r.getdel(_REFRESH_KEY.format(jti=jti)) is None:
        raise _bad_refresh()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _bad_refresh()
    return _issue_pair(settings, r, user_id)


@app.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, r: Redis = Depends(get_redis), settings: Settings = Depends(get_settings)) -> None:
    # Idempotent: an invalid/expired token is already logged out, so still 204.
    try:
        payload = decode_token(settings, body.refresh_token, "refresh")
    except jwt.PyJWTError:
        return
    r.delete(_REFRESH_KEY.format(jti=payload.get("jti", "")))


@app.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    # exclude_unset: only touch fields the client actually sent.
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "display_name" and value is None:
            continue  # display_name is NOT NULL
        setattr(user, field, value)
    db.add(user)
    db.commit()
    return user
