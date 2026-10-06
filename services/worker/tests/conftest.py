import fakeredis
import pytest

from listens_common import testing

testing.configure_test_env()

from listens_common.config import get_settings  # noqa: E402
from listens_common.models import Artist, Track, User  # noqa: E402
from listens_common.storage import get_s3  # noqa: E402


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
    with Session() as db:
        user = User(email="a@x.io", username="a", password_hash="x", display_name="A")
        artist = Artist(name="B")
        db.add_all([user, artist])
        db.commit()
        ids = (user.id, artist.id)

    class Env:
        s3 = get_s3()
        sessions = Session
        redis = fakeredis.FakeRedis(decode_responses=True)
        dir = tmp_path
        user_id, artist_id = ids
        cfg = settings

        @staticmethod
        def add_track(path, status="uploaded", key=None):
            """Register a track whose 'uploaded' source is the given local file."""
            with Session() as db:
                t = Track(artist_id=ids[1], uploader_id=ids[0], title="t", status=status,
                          source_key=key or f"originals/x/{path.name}")
                db.add(t)
                db.commit()
                tid = t.id
            Env.s3.upload_file(str(path), settings.s3_bucket_audio, key or f"originals/x/{path.name}")
            return tid

        @staticmethod
        def track(tid):
            with Session() as db:
                return db.get(Track, tid)

    return Env
