# Shadow Listens

A Spotify-inspired music streaming platform, built as a portfolio project, with original branding
and artwork. Music comes only from files you upload and own, or Creative Commons / royalty-free
tracks (Free Music Archive, Jamendo, etc.). Built in phases, each one finished and tested before
the next starts.

- ✅ **Phase 1 – Foundation:** monorepo, Docker Compose stack, Alembic schema, auth service
  (JWT access + rotating refresh tokens), API gateway.
- ✅ **Phase 2 – Catalogue & streaming:** upload → MinIO → FFmpeg → HLS (96/160/320 kbps), signed
  short-lived stream URLs, web player (queue, seek, volume, quality, prefetch, persistent mini-player), full-text search.
- ⏳ Phase 3 – library & social (playlists, likes, follows, recently played, Home sections) — next.

## Layout

```
.
├── docker-compose.yml          # postgres, redis, minio, migrate, auth, catalogue, stream, worker, frontend, gateway
├── .env.example                # copy to .env
├── gateway/nginx.conf          # single entry point (:8080): /api/auth, /api/catalogue, /api/stream, / -> web app
├── libs/common/                # shared: settings, SQLAlchemy models, JWT/bcrypt, URL signing, S3 helper
│   └── tests/                  # migration-vs-models test, signing tests
├── migrations/                 # Alembic: 0001 schema, 0002 catalogue columns + full-text (GIN) indexes
├── services/
│   ├── auth/                   # register / login / refresh / logout / profile
│   ├── catalogue/               # upload, tracks, artists, albums, search
│   ├── stream/                  # issues signed URLs, serves HLS + covers from private storage
│   └── worker/                  # Redis-Stream consumer: FFmpeg -> HLS renditions + cover art
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

> **Note on MinIO:** the official `minio/minio` Docker Hub image now requires a paid login (MinIO
> restricted free public pulls in 2025). The compose file uses `bitnamilegacy/minio` instead — same
> `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` env vars, and it auto-creates the audio/covers buckets
> via `MINIO_DEFAULT_BUCKETS` on first boot, so no separate init container is needed.

### Import your music folder

```bash
pip install -r scripts/requirements.txt
python scripts/import_folder.py "C:\path\to\Music" -u <username> --license "Personal library" --i-own-the-rights
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
python -m venv .venv
.venv\Scripts\pip install -e "libs/common[web,storage]" -r services/catalogue/requirements.txt pytest httpx fakeredis alembic "moto[server]"   # Windows
# source .venv/bin/activate && pip install ...                                                                                                   # macOS/Linux
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
E2E_BASE_URL=http://localhost:8080 npx playwright test
```

Playwright's bundled Chromium ships without an AAC decoder (confirmed: it plays `audio/mpeg` but not
`audio/mp4;codecs="mp4a.40.2"`), so with the stack's default `HLS_AUDIO_CODEC=aac` the playback assertions
fail there — not an app bug, a missing codec in that specific browser build. Two ways to actually exercise it:
`E2E_BROWSER_CHANNEL=msedge npx playwright test` (uses the real, codec-complete system Edge — this is how
the AAC default was verified below), or set `HLS_AUDIO_CODEC=mp3` in `.env` and use the bundled Chromium as-is.

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
- **HLS playlist paths use `.as_posix()`, not `str(Path)`:** a real Windows-specific bug found during testing — `ffmpeg`
  on Windows wrote literal backslashes into the generated `.m3u8` playlist text (`q96\index.m3u8`), which breaks every
  HLS player since segment references are URLs. Fixed in `services/worker/app/transcode.py`; harmless on Linux too.
- **MinIO image swap** (see note above) — a real-world infra surprise, not a design choice.

## Verified

This was run for real, twice over: once rebuilding Phase 1 from scratch, and again for Phase 2 — on actual Docker Desktop
(Windows), not a simulated or sandboxed substitute.

- `docker compose up --build`: all 9 containers reach healthy/running.
- Full upload → transcode → stream pipeline exercised via curl against the live gateway: register, upload (tags read
  correctly from a real file), poll to `ready`, fetch the signed URL, master playlist, a variant playlist, a segment
  (right content-type and byte count), cover art, full-text search finding the track, a tampered/garbage token → 403,
  an unauthenticated request → 401.
- **Real-world import test:** 8 real MP3s (3–7 minutes each, Tamil film songs with multi-artist tags) copied from the
  user's own `Music` folder, imported via `scripts/import_folder.py` against the live stack. All 8 transcoded to `ready`
  with correct multi-artist tags and realistic durations within ~50 s on a single worker; re-running the import correctly
  skipped all 8 via SHA-256 dedup without re-uploading.
- MinIO bucket contents inspected directly (`mc ls`) — originals, HLS renditions (96/160 kbps; 320 kbps correctly
  skipped for the lower-bitrate sources), and cover art all present at the expected keys.
- **Browser end-to-end** (Playwright): the full flow — register, upload, wait for transcoding, play, pause/resume, seek,
  volume, quality switching, queue (add/next/jump), prefetch (next track needs no new URL request), persistent
  mini-player across page navigation, search, session persistence across reload, logout — passes against the live
  stack, run twice: once with `HLS_AUDIO_CODEC=mp3` (Playwright's bundled Chromium lacks an AAC decoder — confirmed via
  `canPlayType`), and once with the **actual production default**, `HLS_AUDIO_CODEC=aac`, using the real system Edge
  browser (confirmed via `canPlayType` to have full AAC support) — so the real default is verified end-to-end, not just
  the CI-friendly fallback.
- All 55 Python tests (5 + 13 + 7 + 13 + 17 across the five Python packages) and a clean `tsc --noEmit` pass locally,
  outside Docker.
- One genuine bug was found and fixed during this process (not pre-existing, caught by testing on Windows): FFmpeg wrote
  Windows-style backslash paths into generated HLS playlists, which would break playback in any browser. See "Key
  decisions" above.

## Next

Phase 3: playlists (create/edit/reorder/delete, collaborative), likes, follows (artists/users), recently played,
and a Home page with recently-played / made-for-you / new-releases sections.
