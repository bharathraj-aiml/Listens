# Shadow Listens

A Spotify-inspired music streaming platform with original branding. Music comes only from files you
upload and own (or CC / royalty-free tracks). Built in phases:

- ✅ **Phase 1 – Foundation:** monorepo, compose stack, Alembic schema, auth (JWT access + rotating refresh).
- ✅ **Phase 2 – Catalogue & streaming:** upload → MinIO → FFmpeg → HLS (96/160/320 kbps), signed
  short-lived stream URLs, web player (queue, seek, volume, quality, prefetch, persistent mini-player), full-text search.

## Layout

```
.
├── docker-compose.yml          # postgres, redis, minio(+init), migrate, auth, catalogue, stream, worker, frontend, gateway
├── .env.example                # copy to .env
├── gateway/nginx.conf          # single entry point (:8080): /api/auth, /api/catalogue, /api/stream, / -> web app
├── libs/common/                # shared: settings, SQLAlchemy models, JWT/bcrypt, URL signing, S3 helper
├── migrations/                 # Alembic: 0001 schema, 0002 catalogue columns + full-text (GIN) indexes
├── services/
│   ├── auth/                   # register / login / refresh / logout / profile
│   ├── catalogue/              # upload, tracks, artists, albums, search
│   ├── stream/                 # issues signed URLs, serves HLS + covers from private storage
│   └── worker/                 # Redis-Stream consumer: FFmpeg -> HLS renditions + cover art
├── frontend/                   # Next.js 15 · React 19 · TypeScript · Tailwind 4 · Zustand · hls.js (+ Playwright e2e)
└── scripts/import_folder.py    # bulk-import a music folder through the public API
```

## Run

```bash
cp .env.example .env            # change JWT_SECRET and STREAM_SIGNING_SECRET if this will leave your machine
docker compose up --build
```

Open **http://localhost:8080**, register, go to **Upload**, and add a few files. Status goes
*Queued → Processing… → Ready* as the worker transcodes (seconds per track). Then play them from **Home**.
MinIO console (dev only): http://localhost:9001.

Scale transcoding with more workers: `docker compose up --scale worker=3`.

### Import your music folder (e.g. 2.5 GB)

```bash
pip install -r scripts/requirements.txt
python scripts/import_folder.py ~/Music -u <username> --license "Personal library" --i-own-the-rights
# add --dry-run first to see what it would do; --base-url http://<server> for a remote server
```

Re-runnable: each file's SHA-256 is checked with the server first, so already-imported files are skipped
without being re-uploaded. Tags (title/artist/album/genre) are read server-side; untagged files fall back to
the filename and "Unknown Artist". Budget disk for originals **plus** HLS (roughly 1.5–2× the source size).

## What to test

1. **Auth:** register → you land on Home, sign out, sign in (by username or email). `/upload` while signed out redirects to login.
2. **Upload:** pick 2+ files, tick the rights box (the button stays disabled until you do). Watch statuses flip to *Ready*.
   Re-upload the same file → "already uploaded". Upload a text file renamed `.mp3` → it ends *Failed* with a reason.
3. **Player:** play/pause, drag the seek bar, volume, **Quality** (Auto / 96 / 160 / 320 — only renditions that exist
   for that track are listed), next/previous (previous restarts the track if you're >3 s in), the queue panel (jump, remove),
   *Next*/＋ buttons on rows. Navigate between pages while playing: music and mini-player keep going.
4. **Mobile:** open on a phone (or a narrow window): bottom tab bar, compact player, lock-screen controls (Media Session).
5. **Search:** prefix + multi-word, case-insensitive; matching an artist name returns that artist's tracks.
6. **Streaming security:** in dev-tools copy a segment URL; change one character of the token → 403; wait past expiry → 403.
   `POST /api/stream/tracks/<id>/url` without a token → 401.

## Tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "libs/common[web,storage]" -r services/catalogue/requirements.txt \
    pytest httpx fakeredis alembic "moto[server]"
# needs ffmpeg + ffprobe on PATH
(cd libs/common        && pytest)   # signing + "migrations produce exactly the ORM schema"
(cd services/auth      && pytest)
(cd services/catalogue && pytest)   # upload, catalogue, search (SQLite fallback)
(cd services/stream    && pytest)   # signed URLs, path whitelist, expiry/tamper cases
(cd services/worker    && pytest)   # real FFmpeg transcodes, retry/failed/sweep logic

# Postgres full-text search (incl. "planner really uses the GIN indexes" check) needs a real database:
TEST_PG_URL=postgresql+psycopg2://user@localhost:5432/scratch_db  (cd services/catalogue && pytest tests/test_search_postgres.py)
```

Browser end-to-end (register → upload → transcode → play → seek → quality → queue → persistence → search → logout),
against a running stack:

```bash
cd frontend && npm install && npx playwright install chromium
E2E_BASE_URL=http://localhost:8080 npx playwright test       # needs ffmpeg locally to synthesise tones
```
Playwright's bundled Chromium has **no AAC decoder**, so with the default codec the playback steps would fail there. Either point the test
at real Chrome (`E2E_CHROMIUM_PATH=/usr/bin/google-chrome npx playwright test`) or run the stack with `HLS_AUDIO_CODEC=mp3` in `.env`.

## How it works

**Upload pipeline.** `POST /api/catalogue/upload` (multipart) validates extension/size/rights, hashes the file (dedupe per user),
reads tags with `mutagen`, stores the original in MinIO (`originals/<id>/source.ext`), inserts the track as `uploaded`,
and `XADD`s a job to the Redis Stream `jobs:transcode`. A worker (consumer group, at-least-once) atomically claims the track
(`uploaded → processing`), runs `ffprobe` (rejects non-audio), then one FFmpeg run produces AAC renditions as 6 s MPEG-TS
segments + a master playlist, uploads them to `hls/<id>/…`, extracts embedded cover art, and marks the track `ready` (or retries
twice, then `failed` with the reason). A periodic sweep re-queues jobs that were lost or whose worker died.
Renditions above the source's quality are skipped (a 128 kbps MP3 gets 96 + 160, not a pointless 320).

**Signed URLs.** `POST /api/stream/tracks/<id>/url` (JWT) returns `/api/stream/hls/<token>/master.m3u8`. The token (HMAC-SHA256,
track id + expiry) sits in the URL *path*, so every relative reference inside the playlists inherits it with no rewriting
(S3 presigned URLs sign exactly one object, which doesn't work for HLS). The stream service verifies it and reads from the
private bucket itself; only a fixed whitelist of file names is servable. Lifetime = track length + 10 min (15 min – 6 h);
the player transparently re-requests a URL if one expires mid-track.

**Player.** One `<audio>` element lives in the `(app)` layout (so it persists across navigation), driven by a Zustand store.
hls.js handles HLS (Safari uses native HLS). Quality: `Auto` = adaptive; fixed levels switch at the next segment. The next
track's URL, playlists and first segment are prefetched into the HTTP cache ~3 s after a track starts.

**Search.** Postgres `to_tsvector('simple', …) @@ to_tsquery('daft:* & pu:*')` over tracks, artists, albums and playlists
(public + your own), backed by expression GIN indexes (migration 0002) and ranked with `ts_rank`.

## Key decisions

- **Tokens:** access JWT stateless (15 min); refresh JWT stateful in Redis, rotated on use (atomic `GETDEL`), revoked on logout.
- **Why not store audio in Postgres/Git:** blobs belong in object storage; the DB keeps metadata + keys.
- **Redis Streams, not a list:** a job is only removed after it's handled (`XACK`+`XDEL`), and crashed workers' jobs are reclaimed.
- **No FKs on `play_events`; polymorphic `follows`; VARCHAR+CHECK instead of PG enums** (see `libs/common/listens_common/models.py`).
- **Tokens in `localStorage`:** fine for a self-hosted app; production would use httpOnly cookies + CSRF protection.

## What has and hasn't been verified (honest status)

Verified in a no-Docker sandbox with **real** Postgres 16, Redis 7, FFmpeg 6, nginx 1.24 (running the actual `gateway/nginx.conf`),
the production Next.js build, and Playwright/Chromium. A moto S3 server stood in for MinIO. Migrations were run up/down on real Postgres.
Both the API-level and browser-level end-to-end runs pass, and the folder importer was run against the live stack.

**Not verified:** (1) `docker compose up` itself, the Dockerfiles, and the real MinIO / `nginx:alpine` images (no Docker daemon was
available; `docker compose config` validates). If `migrate`, `minio-init`, or a build fails, send me the log. (2) **AAC playback in a
real browser:** the sandbox's Chromium has no AAC decoder, so the browser test ran with `HLS_AUDIO_CODEC=mp3`. The default AAC output
is verified at the stream level (a produced segment is decoded and checked: AAC-LC, 44.1 kHz, stereo) and AAC is what Chrome/Firefox/Edge/Safari
all decode, but please confirm in your browser. (3) Safari/iOS native-HLS path and lock-screen controls, and arm64 images (Oracle VM), are untested.

## Next

Phase 3: playlists (create/edit/reorder/collaborative), likes, follows, recently played, Home sections.
Phase 7 will harden defaults (refuse weak secrets, rate limiting, invite-only signup, 3-device cap) and add the Oracle Cloud deployment guide.
