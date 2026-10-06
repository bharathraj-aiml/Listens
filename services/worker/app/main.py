import logging
import socket

import redis

from listens_common.config import get_settings
from listens_common.db import get_sessionmaker
from listens_common.storage import get_s3

from .jobs import run_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    settings = get_settings()
    # socket_timeout must exceed the blocking XREADGROUP (BLOCK_MS), otherwise an idle queue
    # raises TimeoutError. health_check_interval detects half-dead connections.
    r = redis.Redis.from_url(
        settings.redis_url, decode_responses=True,
        socket_timeout=30, socket_connect_timeout=5, health_check_interval=30,
    )
    consumer = f"worker-{socket.gethostname()}"
    logging.getLogger("worker").info("transcode worker %s started", consumer)
    run_forever(r, get_sessionmaker(), get_s3(), settings, consumer)


if __name__ == "__main__":
    main()
