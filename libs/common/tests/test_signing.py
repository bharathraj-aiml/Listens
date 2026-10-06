import time
import uuid

import pytest

from listens_common.signing import InvalidSignature, sign_token, verify_token

SECRET = "s3cret"


def test_roundtrip():
    tid = uuid.uuid4()
    assert verify_token(SECRET, sign_token(SECRET, "hls", tid, 60), "hls") == tid


def test_rejects_wrong_secret_kind_and_tampering():
    tid = uuid.uuid4()
    tok = sign_token(SECRET, "hls", tid, 60)
    with pytest.raises(InvalidSignature):
        verify_token("other", tok, "hls")
    with pytest.raises(InvalidSignature):
        verify_token(SECRET, tok, "cover")
    body, mac = tok.split(".")
    other_body = sign_token(SECRET, "hls", uuid.uuid4(), 60).split(".")[0]
    with pytest.raises(InvalidSignature):  # valid MAC for a different payload
        verify_token(SECRET, f"{other_body}.{mac}", "hls")


def test_rejects_expired_and_malformed():
    tok = sign_token(SECRET, "hls", uuid.uuid4(), -1)
    with pytest.raises(InvalidSignature):
        verify_token(SECRET, tok, "hls")
    for bad in ("", "abc", "a.b", "....", "%%%.%%%"):
        with pytest.raises(InvalidSignature):
            verify_token(SECRET, bad, "hls")


def test_token_is_path_safe():
    tok = sign_token(SECRET, "hls", uuid.uuid4(), 60, uuid.uuid4())
    assert all(c.isalnum() or c in "-_." for c in tok)
    time.sleep(0)  # (no-op) token contains no '/', '+', '=' so it can sit in a URL path unescaped
