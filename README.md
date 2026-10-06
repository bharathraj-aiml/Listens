# Shadow Listens

A Spotify-inspired music streaming platform, built as a portfolio project, with original branding
and artwork. Music comes only from files you upload and own, or Creative Commons / royalty-free
tracks (Free Music Archive, Jamendo, etc.). Built in phases, each one finished and tested before
the next starts.

- ✅ **Phase 1 – Foundation:** monorepo, Docker Compose stack, Alembic schema, auth service
  (JWT access + rotating refresh tokens), API gateway.
- ⏳ Phase 2 – catalogue & streaming (upload, FFmpeg/HLS, signed URLs, web player, search) — next.

## Layout

```
.
├── docker-compose.yml     # postgres, redis, minio, migrate, auth, gateway
├── .env.example           # copy to .env
├── gateway/nginx.conf     # API gateway: /api/auth/* -> auth service
├── libs/common/           # shared package: settings, SQLAlchemy models, JWT/bcrypt helpers
│   └── tests/             # migration-vs-models test
├── migrations/            # Alembic (one-shot `migrate` container runs `upgrade head`)
└── services/auth/         # FastAPI: register, login, refresh, logout, profile
    └── tests/
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

Gateway: http://localhost:8080 · MinIO console: http://localhost:9001 (credentials in `.env`).

> **Note on MinIO:** the official `minio/minio` Docker Hub image now requires a paid login (MinIO
> restricted free public pulls in 2025). The compose file uses `bitnamilegacy/minio` instead — same
> `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` env vars, and it auto-creates the audio/covers buckets
> via `MINIO_DEFAULT_BUCKETS` on first boot, so no separate init container is needed. MinIO itself
> isn't exercised by any Phase 1 feature yet (Phase 2's upload pipeline is what uses it) — it's
> provisioned now so Phase 2 has buckets ready to go.

### Try it

```bash
B=http://localhost:8080/api/auth
curl -s $B/register -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","username":"ada","password":"correct horse battery"}'
curl -s $B/login -H 'content-type: application/json' \
  -d '{"identifier":"ada","password":"correct horse battery"}'          # -> access + refresh tokens
curl -s $B/me -H "authorization: Bearer <access_token>"
curl -s -X PATCH $B/me -H "authorization: Bearer <access_token>" -H 'content-type: application/json' -d '{"bio":"hi"}'
curl -s $B/refresh -H 'content-type: application/json' -d '{"refresh_token":"<refresh_token>"}'
curl -s -X POST $B/logout -H 'content-type: application/json' -d '{"refresh_token":"<refresh_token>"}'
```

Interactive API docs for the service are not exposed through the gateway; to see them, temporarily
publish port 8000 on `auth`, or run it directly (below) and open `/docs`.

## What to test

1. **Register** → 201, email lowercased, no password/hash in the response.
2. **Duplicate register** (same email or username, any case) → 409.
3. **Login** by username or by email, case-insensitive → access + refresh tokens.
4. **Wrong password / unknown user** → both 401 with the *same* error body (doesn't leak which accounts exist).
5. **`GET /me`** with the access token → your profile; with the refresh token or no token → 401.
6. **`PATCH /me`** updates bio/display name; partial updates leave other fields alone.
7. **Refresh rotation:** refresh once (new pair), then replay the *old* refresh token → 401.
8. **Logout** revokes the refresh token immediately (next refresh with it → 401).
9. **Restart resilience:** `docker compose restart auth gateway`, then log in again — data in
   Postgres/Redis volumes survives (verified: works).
10. **Schema check:** `docker compose exec postgres psql -U listens -d listens -c '\dt'` → all 9
    tables + `alembic_version`.

All ten were run against this exact stack in real Docker Desktop (not simulated) before this was handed off — see "Verified" below.

## Tests (no Docker needed)

Unit tests use in-memory SQLite and fakeredis.

```bash
python -m venv .venv
.venv\Scripts\pip install -e libs/common -r services/auth/requirements.txt pytest httpx fakeredis alembic   # Windows
# source .venv/bin/activate && pip install ...                                                               # macOS/Linux
(cd libs/common && pytest)     # migration produces exactly the ORM schema; downgrade is clean
(cd services/auth && pytest)   # 13 auth tests
```

## Key design decisions

- **Shared `listens_common` package** holds the models, so every service and Alembic see one schema.
  (Trade-off: services are coupled at the schema level. Fine for a monolith-ish start; Phase 7 notes the split.)
- **Access tokens are stateless (15 min); refresh tokens are stateful (7 days)** – each has a `jti` stored in
  Redis. Refresh *rotates* (old token consumed atomically with `GETDEL`), logout deletes the key, so revocation is
  immediate while other services can still verify access tokens with only the shared secret.
- **bcrypt directly** (not passlib, which is unmaintained); passwords over 72 bytes are rejected, not truncated.
- **Login errors are uniform** for unknown user vs. wrong password.
- **Status/type columns are VARCHAR + CHECK**, not PG enums, for painless migrations.
- **`follows` is polymorphic** (user or artist target) so `target_id` has no FK.
- `play_events` has no FKs: high-volume append-only log that should outlive deleted users/tracks.
- **MinIO image swap** (see note above) — a real-world infra surprise, not a design choice; documented
  so it isn't mistaken for a lapse if you look closely at the compose file.

## Verified

Unlike a typical "trust me" handoff, this was run for real: `docker compose up --build` on actual
Docker Desktop (Windows), all 5 containers reaching healthy, all 10 "what to test" items exercised
with curl against the live gateway, the Postgres schema inspected directly, and a mid-session
service restart confirmed data survives. Both pytest suites (14 tests total) pass locally outside
Docker too.

## Next

Phase 2: upload → MinIO → FFmpeg (HLS at 96/160/320 kbps) → signed streaming URLs, the Next.js web
player (queue, seek, volume, quality switching, persistent mini-player), and Postgres full-text search.
