"""Scheduled ALS training loop. No Redis stream here, unlike worker/events - this is a batch
job over the whole interactions table on a timer, not a per-item queue consumer, so a plain
sleep loop is the right tool (same reasoning that justified events as its own service in
Phase 4: a genuinely different kind of process from a request/response API)."""
import logging
import time

from listens_common.config import get_settings
from listens_common.db import get_sessionmaker

from . import train

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("recommender")


def run_forever() -> None:
    settings = get_settings()
    sessions = get_sessionmaker()
    interval_s = settings.recommender_train_interval_hours * 3600

    while True:
        try:
            with sessions() as db:
                train.train(db)
        except Exception:  # noqa: BLE001 - a failed training run must never kill the loop
            log.exception("ALS training run failed; will retry next cycle")
        time.sleep(interval_s)


if __name__ == "__main__":
    run_forever()
