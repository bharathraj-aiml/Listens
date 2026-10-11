"""HTTP entrypoint for ALS training, for deployments that can't run a long-lived process (see
services/worker/app/http.py for the full rationale). docker-compose keeps using run_forever()'s
sleep loop unchanged for local/self-hosted runs. Unlike worker/events there's no Redis stream to
drain here - just one training run per tick, meant to be triggered on a daily schedule (see
.github/workflows/cron-tick.yml), matching RECOMMENDER_TRAIN_INTERVAL_HOURS's default.
"""
import logging

from fastapi import Depends, FastAPI

from listens_common.db import get_sessionmaker

from . import train

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("recommender-http")

app = FastAPI(title="Shadow Listens - Recommender (HTTP-triggered)")


def get_sessions():
    return get_sessionmaker()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tick")
def tick(sessions=Depends(get_sessions)) -> dict:
    try:
        with sessions() as db:
            train.train(db)
    except Exception:  # noqa: BLE001 - a failed run must still answer the caller, not 500 forever
        log.exception("ALS training run failed")
        return {"trained": False}
    return {"trained": True}
