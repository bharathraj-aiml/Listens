import fakeredis
import pytest

from listens_common import testing


@pytest.fixture
def env():
    sessions = testing.sqlite_sessionmaker()
    redis_fake = fakeredis.FakeRedis(decode_responses=True)

    class Env:
        sessions_ = sessions
        redis = redis_fake

    return Env
