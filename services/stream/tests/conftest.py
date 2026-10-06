import pytest
from fastapi.testclient import TestClient

from listens_common import testing

testing.configure_test_env()

from app.main import app  # noqa: E402
from listens_common.config import get_settings  # noqa: E402
from listens_common.db import get_db  # noqa: E402
from listens_common.models import Artist, Track, User  # noqa: E402


@pytest.fixture(scope="session")
def s3_server():
    server = testing.start_s3_server()
    testing.make_buckets(get_settings())
    yield server
    server.stop()


@pytest.fixture
def env(s3_server):
    settings = get_settings()
    testing.clear_buckets(settings)
    Session = testing.sqlite_sessionmaker()

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    with Session() as db:
        user = User(email="a@x.io", username="a", password_hash="x", display_name="A")
        artist = Artist(name="B")
        db.add_all([user, artist])
        db.flush()
        ready = Track(artist_id=artist.id, title="r", status="ready", duration_ms=200_000, cover_key="tracks/c.jpg")
        pending = Track(artist_id=artist.id, title="p", status="processing")
        nocover = Track(artist_id=artist.id, title="n", status="ready")
        db.add_all([ready, pending, nocover])
        db.commit()
        ids = dict(user=user.id, ready=ready.id, pending=pending.id, nocover=nocover.id)

    class Env:
        client = TestClient(app)
        headers = testing.auth_header(settings, ids["user"])
        settings_ = settings
        s3 = __import__("listens_common.storage", fromlist=["get_s3"]).get_s3()

    Env.ids = ids
    yield Env
    app.dependency_overrides.clear()
