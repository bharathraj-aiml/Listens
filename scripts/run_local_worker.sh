#!/usr/bin/env bash
# Runs the transcode worker on this machine against the PRODUCTION Neon/Upstash/B2 (values in the
# gitignored .env.prod). Use it while the laptop is on; Render's worker is the fallback when it's
# off - each queued job goes to exactly one worker, and a job abandoned by a switched-off laptop
# is reclaimed by Render's worker after ~10 minutes. Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env.prod; set +a
# Windows decodes ffprobe output as cp1252 by default and crashes on non-English song tags;
# force UTF-8 like the Linux containers use.
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export OPENBLAS_NUM_THREADS=1 NUMBA_CACHE_DIR="${TMPDIR:-/tmp}/numba_cache"
cd services/worker
exec ../../.venv/Scripts/python -m app.main
