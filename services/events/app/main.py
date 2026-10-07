import logging
import socket

import redis

from listens_common.config import get_settings
from listens_common.db import get_sessionmaker

from .consumer import run_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    settings = get_settings()
    r = redis.Redis.from_url(
        settings.redis_url, decode_responses=True,
        socket_timeout=30, socket_connect_timeout=5, health_check_interval=30,
    )
    consumer = f"events-{socket.gethostname()}"
    logging.getLogger("events").info("events consumer %s started", consumer)
    run_forever(r, get_sessionmaker(), consumer)


if __name__ == "__main__":
    main()
