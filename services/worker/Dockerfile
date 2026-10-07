FROM python:3.12-slim
WORKDIR /srv
# OPENBLAS_NUM_THREADS=1: librosa/numpy's BLAS backend spawning its own thread pool inside an
# already-threaded worker process causes severe contention (the same warning implicit's ALS
# gives in services/recommender - same root cause, same fix).
# NUMBA_CACHE_DIR: librosa's numba-jitted functions use @jit(cache=True), which by default
# writes its compiled-code cache next to the source file in site-packages - not writable by
# the non-root "app" user below, so every container run would fail with "cannot cache
# function: no locator available" the moment a track was actually processed (unit tests never
# catch this since they run as a normal user with full site-packages write access).
ENV PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 PIP_DEFAULT_TIMEOUT=100 NUMBA_CACHE_DIR=/tmp/numba_cache
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY libs/common /libs/common
# Cache mount (not image layer): wheels persist across retries without bloating the final
# image. librosa pulls in a ~60MB llvmlite wheel that can outlast a single read-timeout
# window on a slow link; without this, each retry re-downloaded everything from zero.
RUN --mount=type=cache,target=/root/.cache/pip pip install "/libs/common[storage]"
COPY services/worker/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY services/worker/app ./app
RUN useradd -r app && chown -R app /srv
USER app
CMD ["python", "-m", "app.main"]
