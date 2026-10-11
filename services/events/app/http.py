"""HTTP entrypoint for the events consumer, for deployments that can't run a long-lived process
(see services/worker/app/http.py for the full rationale - same pattern, applied here).
docker-compose keeps using consumer.run_forever() unchanged for local/self-hosted runs.
"""
import logging
import socket
import time

import redis
from fastapi import Depends, FastAPI

from listens_common.config import get_settings
from listens_common.db import get_sessionmaker

from . import consumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("events-http")

app = FastAPI(title="Shadow Listens - Events (HTTP-triggered)")
_consumer_name = f"events-{socket.gethostname()}"


def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(
        settings.redis_url, decode_responses=True,
        socket_timeout=15, socket_connect_timeout=5, health_check_interval=30,
    )


def get_sessions():
    return get_sessionmaker()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tick")
def tick(
    max_seconds: float = 30,
    block_ms: int = 1000,
    r: redis.Redis = Depends(get_redis),
    sessions=Depends(get_sessions),
) -> dict:
    """Reclaim stuck messages, then drain the stream (up to 10 events per poll) until it's
    empty or max_seconds elapses. Each event is a single small insert, so this is cheap and
    fast - a generous max_seconds is mostly a safety cap, not an expected duration."""
    consumer.ensure_group(r)
    consumer.sweep(r, sessions, _consumer_name)

    start = time.monotonic()
    handled = 0
    while time.monotonic() - start < max_seconds:
        n = consumer.poll_once(r, sessions, _consumer_name, block_ms=block_ms)
        if n == 0:
            break
        handled += n
    log.info("tick handled %d event(s)", handled)
    return {"handled": handled}
