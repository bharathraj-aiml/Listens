# Shadow Listens

A Spotify-inspired music streaming platform, built as a portfolio project, with original branding
and artwork. Music comes only from files you upload and own, or Creative Commons / royalty-free
tracks (Free Music Archive, Jamendo, etc.). Built in phases, each one finished and tested before
the next starts.

- ✅ **Phase 1 – Foundation:** monorepo, Docker Compose stack, Alembic schema, auth service
  (JWT access + rotating refresh tokens), API gateway.
- ✅ **Phase 2 – Catalogue & streaming:** upload → MinIO → FFmpeg → HLS (96/160/320 kbps), signed
  short-lived stream URLs, web player (queue, seek, volume, quality, prefetch, persistent mini-player), full-text search.
- ✅ **Phase 3 – Library & social:** playlists (CRUD, reorder, collaborative), likes, follows,
  recently played, Home sections (recently played / made for you / new uploads), synced lyrics.
- ✅ **Phase 4 – Event tracking:** play/skip events → Redis Streams → a consumer service, verified
  streams (30s threshold), and an analytics page (top tracks, skip rate, listening by hour).
- ✅ **Phase 5 – Recommendations:** implicit-feedback ALS (nightly `recommender` service), ALS-ranked
  "made for you" (max 2 per artist), "similar tracks" via vector cosine similarity, cold-start
  fallback via `librosa` tempo/energy then same-artist/genre.
- ⏳ Phase 6 – smart shuffle (artist-spreading shuffle vs. Fisher–Yates) — next.

## Layout

```
.
├── docker-compose.yml          # postgres, redis, minio, migrate, auth, catalogue, stream, worker, events, recommender, frontend, gateway
├── .env.example                # copy to .env
├── gateway/nginx.conf          # single entry point (:8080): /api/auth, /api/catalogue, /api/stream, / -> web app
├── libs/common/                # shared: settings, SQLAlchemy models, JWT/bcrypt, URL signing, S3 helper
│   └── tests/                  # migration-vs-models test, signing tests
├── migrations/                 # Alembic: 0001 schema, 0002 catalogue + full-text (GIN), 0003 lyrics, 0004 audio features + vectors
├── services/
│   ├── auth/                   # register / login / refresh / logout / profile
│   ├── catalogue/               # upload, tracks, artists, albums, search, playlists, likes, follows, lyrics, home, events ingest, analytics, recommendations
│   ├── stream/                  # issues signed URLs, serves HLS + covers from private storage
│   ├── worker/                  # Redis-Stream consumer: FFmpeg -> HLS renditions + cover art + librosa audio features
│   ├── events/                  # Redis-Stream consumer: play/skip events -> play_events rows
│   └── recommender/              # scheduled job: builds the interaction matrix, trains ALS, writes user/track vectors
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
7. **Likes:** heart a track from any list or the player bar; it stays highlighted after a reload.
8. **Playlists:** create one, add tracks (from a track row's playlist icon), reorder with the up/down arrows, rename, make it
   public/collaborative, and — from a second account — confirm you can add/reorder tracks on a collaborative playlist but
   can't rename or delete it. Delete it from the owner account.
9. **Follow:** on an artist page, Follow/Following toggles and persists.
10. **Home sections:** Recently played (after you've played something), Made for you (never empty, even for a brand-new
    account — it falls back to new releases), New uploads.
11. **Lyrics:** open the lyrics panel (text icon next to the queue icon) on any track. Most files show "No lyrics available"
    unless they have embedded ID3 `USLT`/`SYLT` tags (or Vorbis/MP4 equivalents) — see the note under "How it works".
12. **Analytics:** play a track for 30+ seconds (check it against the Network tab: a `play_end` event with `ms_played >= 30000`
    fires on the next track change), then check the Analytics page — it should show up under *Top tracks*. Click Next on a
    track and confirm a `skip` event fires with `reason: "next_button"`. Skip rate needs at least 2 plays of a track to appear.
13. **Similar tracks:** open the similar-tracks panel (sparkle icon next to the queue icon) on any playing track — it never
    shows the track itself. Brand-new uploads with no listening history yet fall back to tempo/energy proximity, then
    same-artist/genre, so the panel is never empty as long as *some* other ready track exists.
14. **Made for you:** once `services/recommender` has trained at least once (immediately on stack startup, then every
    `RECOMMENDER_TRAIN_INTERVAL_HOURS`), a user with enough listening history gets ALS-ranked picks, capped at 2 per
    artist; everyone else still sees the Phase 3 heuristic/new-releases fallback — the section is never empty.


## Tests

```bash
python -m venv .venv
.venv\Scripts\pip install -e "libs/common[web,storage]" -r services/catalogue/requirements.txt -r services/worker/requirements.txt -r services/recommender/requirements.txt pytest httpx fakeredis alembic "moto[server]"   # Windows
# source .venv/bin/activate && pip install ...                                                                                                   # macOS/Linux
# needs ffmpeg + ffprobe on PATH; set OPENBLAS_NUM_THREADS=1 to avoid BLAS/thread-pool contention under pytest
(cd libs/common        && pytest)   # signing + "migrations produce exactly the ORM schema"
(cd services/auth      && pytest)
(cd services/catalogue && pytest)   # upload, catalogue, search, playlists, likes, follows, lyrics, events, analytics, recommendations
(cd services/stream    && pytest)   # signed URLs, path whitelist, expiry/tamper cases
(cd services/worker    && pytest)   # real FFmpeg transcodes, retry/failed/sweep logic, librosa audio-feature extraction
(cd services/events    && pytest)   # Redis Stream consumer: insert/retry/drop/sweep logic
(cd services/recommender && pytest) # matrix weighting/clamping, ALS training + vector persistence, a block-structure correctness check

# Postgres full-text search (incl. "planner really uses the GIN indexes" check) needs a real database:
TEST_PG_URL=postgresql+psycopg2://user@localhost:5432/scratch_db  (cd services/catalogue && pytest tests/test_search_postgres.py)
```

Browser end-to-end, against a running stack - four specs: the core player flow (register → upload →
transcode → play → seek → quality → queue → persistence → search → logout), playlists/likes/follow/lyrics,
and two covering events/analytics (the client fires the right event with the right reason; the analytics
page renders seeded data correctly):

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

**Library & social.** Playlists, likes, follows and `play_events` are all Phase-1 tables; Phase 3 is purely new endpoints
over them (`services/catalogue/app/library.py`), no new microservice. A playlist is visible to everyone if `is_public`,
otherwise only to its owner; any authenticated user can add/remove/reorder tracks on an `is_collaborative` playlist (there's
no per-playlist member list — "collaborative" means "anyone with an account on this server"). Reordering renumbers the whole
list by position, which is fine at personal-playlist sizes. "Made for you" is a heuristic (liked/played artists, excluding
already-played tracks, falling back to newest releases so it's never empty) — real ALS recommendations are Phase 5.

**Lyrics.** Read at upload time with `mutagen`: ID3 `USLT` (plain) and `SYLT` (time-synced, converted to LRC
`[mm:ss.xx]text` lines; only millisecond-based `SYLT` timing can be converted — frame-based timing is skipped, not
guessed), or the equivalent Vorbis/MP4 tags as a fallback. Served on demand via `GET /tracks/<id>/lyrics` rather than
embedded in every track response. The player's Lyrics panel highlights the current synced line against playback position.
**Most files won't have any of this** — checked across the 160 real MP3s used for Phase 2 testing, zero had embedded
lyrics in any common frame, so expect "No lyrics available" unless a file was tagged with a tool that writes `USLT`/`SYLT`.

**Event tracking.** `POST /api/catalogue/events` (play_start / play_end / skip) `XADD`s to the Redis Stream `jobs:events`
and returns immediately - it's a hot path (fires on every track load and every skip), so it doesn't wait on a database
write. A dedicated `events` service (the same consumer-group pattern as the transcode worker) drains that stream into
`play_events`. `like` and `add_to_playlist` aren't client-submittable event types; they're published server-side as a
side effect of the existing `/likes` and `/playlists/*/tracks` endpoints, so there's one write path per mutation, not two.
The player tracks actual played-time per track from `timeupdate` deltas (clamped per tick so a seek can't inflate it),
and tags the outgoing track's closing event as `play_end` (natural completion, via the `ended` handler) or `skip` (an
explicit reason - `next_button` / `previous_button` / `track_select` - threaded through the player store by whichever
action caused the change). A "stream" only counts for the Analytics page once `ms_played >= 30000`.

**Recommendations.** `services/recommender` builds a weighted user×track interaction matrix from
`play_events`/`likes`/`playlist_tracks` — a full listen (≥90% of duration) is +1, every repeat full
listen beyond the first is an additional +2, a save (like or playlist-add) is +3, an early skip
(<30s in) is −2, summed per pair and clamped to ≥0 (confidence-weighted implicit ALS needs
non-negative input; a heavily-skipped track just contributes no positive signal rather than being
fed as a literal negative). It trains `implicit`'s `AlternatingLeastSquares` on that matrix
immediately on startup and every `RECOMMENDER_TRAIN_INTERVAL_HOURS` after (default 24h — "nightly"),
storing the resulting user/track latent-factor vectors as plain JSON arrays (`user_vectors`,
`track_vectors`) rather than a Postgres-specific `ARRAY` or a vector-DB extension, so the schema
stays portable to SQLite in tests. `services/catalogue/app/recommendations.py` scores "made for
you" as a dot product of a user's vector against every unplayed ready track's vector (capped at 2
tracks per artist), falling back to the Phase 3 heuristic when a user has no vector yet; "similar
tracks" is cosine similarity between two tracks' vectors, falling back to z-scored tempo/energy
proximity (`services/worker/app/audio_features.py`, extracted via `librosa` at upload time) and
then same-artist/genre for a track with no vector and no usable audio features. The ALS math
itself — the confidence/preference split, the alternating-least-squares derivation, why it
converges — is explained in detail in code comments in `services/recommender/app/train.py`, per
the original spec's request to show the maths, not just use the library.

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
- **Python's `0 or -1` falsy-zero trap:** the first track added to a playlist (position 0) was getting duplicated at
  position 0 again, because `(max_position or -1) + 1` treats a real `0` the same as "no rows yet". Fixed to an explicit
  `is None` check; covered by a regression test.
- **Redis Stream fields are always strings:** `PlayEvent.user_id`/`track_id` are typed `Uuid` columns, so the events
  consumer needs an explicit `uuid.UUID(...)` conversion - passing the raw string straight through raised deep inside
  SQLAlchemy's parameter binding. Same bug class the transcode worker didn't have (it never round-trips UUIDs through
  Redis), caught immediately by the consumer's own test suite.
- **CSS percentage heights need a definite-height ancestor:** the listening-by-hour bar chart's columns are sized by
  content (`items-end`, no stretch), so a bar using `height: X%` had nothing to resolve against and silently rendered
  at 0px. Fixed to a computed pixel height. Caught only by looking at an actual screenshot - the e2e test checked the
  bars' `data-count` attributes, which were correct, not their rendered geometry, which wasn't.
- **`libgomp.so.1` missing at runtime:** `implicit`'s compiled ALS extension is linked against OpenMP, which the
  `python:3.12-slim` base image doesn't ship; `services/recommender` crash-looped on `import implicit.als` in the real
  container even though every local/pytest run (run as a normal user with a differently-resolved environment) was fine.
  Fixed by installing `libgomp1` via apt. Only surfaced once actually deployed via Docker — exactly why this phase's
  plan called for a real container rebuild, not just local pytest, before calling it done.
- **`numba` JIT caching needs a writable cache dir:** `librosa`'s internal `@jit(cache=True)` functions try to write
  their compiled-code cache next to the source file in `site-packages` by default — not writable by the non-root `app`
  user the worker container runs as, so every real upload failed audio-feature extraction with "cannot cache function:
  no locator available" (silently, since extraction is deliberately non-fatal — it only showed up by checking
  `tempo_bpm`/`energy` actually landed in Postgres after a real upload, not from any test or log scan). Fixed by
  pointing `NUMBA_CACHE_DIR` at `/tmp`. Local pytest never caught this either, for the same root cause as the
  `libgomp1` bug: it runs as a normal user with full write access to `site-packages`.
- **A capped recommendation list can get "topped up" past its cap:** made-for-you's ALS path correctly capped results
  to 2 tracks per artist, but the heuristic/new-releases fallback that fills remaining slots when ALS doesn't have
  enough data didn't know about that cap, so a thin ALS result could end up right back over the limit. Fixed by
  re-applying the cap once, after all three tiers (ALS, heuristic, fallback) are combined. Caught by a dedicated test
  seeding one artist with more tracks than the cap allows.

## Verified

This was run for real, four times over: rebuilding Phase 1 from scratch, Phase 2, Phase 3, and Phase 4 — on actual
Docker Desktop (Windows), not a simulated or sandboxed substitute.

- `docker compose up --build`: all 10 containers reach healthy/running.
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
- All 117 Python tests (5 + 13 + 53 + 7 + 17 + 9 + 13 across the seven Python packages) and a clean `tsc --noEmit`/
  `next build` pass locally, outside Docker.
- **Phase 3:** a full backend flow via curl against the live stack (lyrics extraction and retrieval, likes, follows,
  a collaborative playlist edited by a second account, reorder, recently-played ordering, made-for-you fallback); a
  Playwright spec covering playlists/likes/follow/lyrics; the Phase 2 player spec updated for the new multi-section
  Home page and rerun 4× consecutively *without* resetting the database to confirm no cross-run flakiness; screenshots
  confirming synced-lyrics highlighting tracks real playback position.
- **Phase 4:** the full events pipeline exercised via curl/Python against the live stack using a real uploaded track
  (events → Redis Stream → the events consumer → Postgres → analytics endpoints, all independently confirmed); two new
  Playwright specs (the client fires the right event with the right reason, confirmed via network interception; the
  analytics page renders seeded top-tracks/skip-rate/listening-by-hour data correctly); all four e2e specs passing
  together from a clean database; a screenshot that caught the bar-chart CSS bug above.
- **Phase 5:** migration 0004 (audio-feature columns + vector tables) verified on both SQLite (models-equivalence
  test) and real Postgres (upgrade → downgrade → upgrade cycle on a disposable container); a full clean rebuild from
  zero (`docker compose down`, every project image deleted, all Docker build cache pruned, every image rebuilt with
  `--no-cache`) — all 11 containers reach healthy/running including the new `recommender` service; a real upload
  through the live gateway confirmed `tempo_bpm`/`energy` land in Postgres after the fix below; `recommender` logged
  a real successful ALS training run against genuine accumulated interaction data; `/home/made-for-you` and
  `/tracks/<id>/similar` exercised via curl against the live stack, both the ALS path and every cold-start fallback
  tier; a new Playwright assertion opens the similar-tracks panel against the live stack and a screenshot confirms it
  renders correctly. Two real bugs only reproduced inside the actual container (never in local pytest, which runs
  under a different user/permissions model) — `libgomp.so.1` missing for `implicit`, and `numba`'s JIT cache needing
  a writable directory for `librosa` — plus a made-for-you artist-cap leak caught by a dedicated test. All described
  under "Key decisions" and covered by regression tests.
- Across all five phases, seven genuine bugs were found and fixed during this process (not pre-existing, caught by
  testing): FFmpeg wrote Windows-style backslash paths into generated HLS playlists (Phase 2); `0 or -1` duplicated a
  playlist's first track position (Phase 3); a UUID-as-string type mismatch and a CSS percentage-height bug (both
  Phase 4); missing `libgomp.so.1`, a non-writable `numba` JIT cache directory, and a made-for-you artist-cap leak
  (all Phase 5, all only caught by testing the real Docker container, not local pytest).

## Next

Phase 6: a smart-shuffle algorithm that spreads an artist's tracks out across a shuffled queue instead of plain
Fisher–Yates (which can cluster the same artist back-to-back by chance), a small script measuring same-artist
adjacency to show the difference is real, and an optional recommendation-injected "smart shuffle" mode.
