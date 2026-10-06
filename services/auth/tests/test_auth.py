import time

import jwt

from listens_common.config import get_settings
from tests.conftest import USER


def auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_register_normalises_email_and_hides_hash(client):
    r = client.post("/register", json=USER)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ada@example.com"
    assert body["display_name"] == "ada_l"
    assert "password" not in body and "password_hash" not in body


def test_register_duplicates_conflict_case_insensitively(client, registered):
    r = client.post("/register", json={**USER, "username": "other", "email": "ADA@example.com"})
    assert r.status_code == 409
    r = client.post("/register", json={**USER, "email": "new@example.com", "username": "ADA_L"})
    assert r.status_code == 409


def test_register_validation(client):
    assert client.post("/register", json={**USER, "password": "short"}).status_code == 422
    assert client.post("/register", json={**USER, "password": "x" * 73}).status_code == 422
    assert client.post("/register", json={**USER, "username": "a b"}).status_code == 422
    assert client.post("/register", json={**USER, "email": "nope"}).status_code == 422


def test_login_by_username_and_email(client, registered):
    for ident in ("ada_l", "ada@example.com", "ADA@EXAMPLE.COM"):
        r = client.post("/login", json={"identifier": ident, "password": USER["password"]})
        assert r.status_code == 200, ident
        assert r.json()["token_type"] == "bearer"


def test_login_failures_are_indistinguishable(client, registered):
    wrong_pw = client.post("/login", json={"identifier": "ada_l", "password": "nope-nope-nope"})
    no_user = client.post("/login", json={"identifier": "ghost", "password": "nope-nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_me_requires_valid_access_token(client, tokens):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    # a refresh token must not work as an access token
    bad = {"Authorization": f"Bearer {tokens['refresh_token']}"}
    assert client.get("/me", headers=bad).status_code == 401
    r = client.get("/me", headers=auth(tokens))
    assert r.status_code == 200 and r.json()["username"] == "ada_l"


def test_expired_access_token_rejected(client, tokens):
    s = get_settings()
    payload = jwt.decode(tokens["access_token"], s.jwt_secret, algorithms=["HS256"])
    payload["exp"] = int(time.time()) - 10
    expired = jwt.encode(payload, s.jwt_secret, algorithm="HS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_update_profile(client, tokens):
    r = client.patch("/me", json={"bio": "hello", "display_name": "Ada"}, headers=auth(tokens))
    assert r.status_code == 200
    assert r.json()["bio"] == "hello" and r.json()["display_name"] == "Ada"
    # partial update leaves other fields alone
    r = client.patch("/me", json={"bio": None}, headers=auth(tokens))
    assert r.json()["bio"] is None and r.json()["display_name"] == "Ada"
    assert client.patch("/me", json={"display_name": ""}, headers=auth(tokens)).status_code == 422


def test_refresh_rotates_and_old_token_is_dead(client, tokens):
    r = client.post("/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    # replaying the old refresh token fails
    assert client.post("/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    # the new one works, and the new access token is valid
    assert client.get("/me", headers=auth(new)).status_code == 200
    assert client.post("/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200


def test_refresh_rejects_access_token_and_garbage(client, tokens):
    assert client.post("/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert client.post("/refresh", json={"refresh_token": "garbage"}).status_code == 401


def test_logout_revokes_refresh_token_and_is_idempotent(client, tokens):
    assert client.post("/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/logout", json={"refresh_token": "garbage"}).status_code == 204


def test_refresh_tokens_have_ttl_in_redis(client, tokens):
    keys = client.redis.keys("refresh:*")
    assert len(keys) == 1
    assert 0 < client.redis.ttl(keys[0]) <= 7 * 86400


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
