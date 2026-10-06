import fakeredis
import pytest
from fastapi.testclient import TestClient

from listens_common import testing

testing.configure_test_env()  # must run before the app (and cached settings) are imported

from app.main import app  # noqa: E402
from listens_common.config import get_settings  # noqa: E402
from listens_common.db import get_db  # noqa: E402
from listens_common.models import User  # noqa: E402
from listens_common.web import get_redis  # noqa: E402


@pytest.fixture(scope="session")
def s3_server():
    server = testing.start_s3_server()
    testing.make_buckets(get_settings())
    yield server
    server.stop()


@pytest.fixture
def env(s3_server, tmp_path):
    settings = get_settings()
    testing.clear_buckets(settings)
    Session = testing.sqlite_sessionmaker()
    redis_fake = fakeredis.FakeRedis(decode_responses=True)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = lambda: redis_fake
    with Session() as db:
        user = User(email="a@x.io", username="a", password_hash="x", display_name="A")
        other = User(email="b@x.io", username="b", password_hash="x", display_name="B")
        db.add_all([user, other])
        db.commit()
        ids = (user.id, other.id)

    class Env:
        client = TestClient(app)
        redis = redis_fake
        sessions = Session
        user_id, other_id = ids
        headers = testing.auth_header(settings, ids[0])
        other_headers = testing.auth_header(settings, ids[1])
        dir = tmp_path

    yield Env
    app.dependency_overrides.clear()
