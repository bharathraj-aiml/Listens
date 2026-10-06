# Shadow Listens

A Spotify-inspired music streaming platform (original branding, royalty-free / user-owned music only).
Built in phases; this is **Phase 1 – Foundation**.

## Layout

```
.
├── docker-compose.yml        # postgres, redis, minio, migrate, auth, gateway
├── .env.example              # copy to .env
├── gateway/nginx.conf        # API gateway: /api/auth/* -> auth service
├── libs/common/              # shared package: settings, SQLAlchemy models, JWT/bcrypt helpers
│   └── tests/                # migration-vs-models test
├── migrations/               # Alembic (one-shot `migrate` container runs `upgrade head`)
└── services/auth/            # FastAPI: register, login, refresh, logout, profile
    └── tests/
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

Gateway: http://localhost:8080 · MinIO console: http://localhost:9001 (credentials in `.env`).

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

## Tests (no Docker needed)

Unit tests use in-memory SQLite and fakeredis.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e libs/common -r services/auth/requirements.txt pytest httpx fakeredis alembic
(cd libs/common && pytest)     # migration produces exactly the ORM schema; downgrade is clean
(cd services/auth && pytest)   # 13 auth tests
```

Inspect the real Postgres schema: `docker compose exec postgres psql -U listens -c '\dt'`

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

## Not verified yet

The compose file passes `docker compose config`, and the Python code is tested on SQLite. The migration has
**not** been executed against real Postgres in my environment (no Docker daemon there) – your first
`docker compose up` is that test. If `migrate` fails, send me its logs.
