import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.deps import get_db, get_redis
from app.main import app
from listens_common.models import Base


@pytest.fixture
def client():
    # In-memory SQLite shared across the TestClient's threads.
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    redis_fake = fakeredis.FakeRedis(decode_responses=True)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = lambda: redis_fake
    with TestClient(app) as c:
        c.redis = redis_fake
        yield c
    app.dependency_overrides.clear()


USER = {"email": "Ada@Example.com", "username": "ada_l", "password": "correct horse battery"}


@pytest.fixture
def registered(client):
    r = client.post("/register", json=USER)
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def tokens(client, registered):
    r = client.post("/login", json={"identifier": USER["username"], "password": USER["password"]})
    assert r.status_code == 200
    return r.json()
