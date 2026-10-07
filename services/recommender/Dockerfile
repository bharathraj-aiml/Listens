FROM python:3.12-slim
WORKDIR /srv
# OPENBLAS_NUM_THREADS=1: implicit's ALS (and the numpy/scipy under it) spawning its own BLAS
# thread pool inside an already-threaded process causes severe contention - same fix as
# services/worker's librosa (see that Dockerfile).
ENV PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 PIP_DEFAULT_TIMEOUT=100
# libgomp1: implicit's compiled ALS extension is linked against OpenMP, which the slim base
# image doesn't ship - without it, "import implicit.als" fails at runtime with
# "ImportError: libgomp.so.1: cannot open shared object file".
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY libs/common /libs/common
RUN --mount=type=cache,target=/root/.cache/pip pip install /libs/common
COPY services/recommender/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY services/recommender/app ./app
RUN useradd -r app && chown -R app /srv
USER app
CMD ["python", "-m", "app.main"]
