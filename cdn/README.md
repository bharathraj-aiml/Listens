# Shadow Listens CDN (Cloudflare in front of Backblaze B2)

A Cloudflare Worker that serves HLS segments, playlists and covers from Cloudflare's cache and only
reads Backblaze B2 the first time a file is requested. Backblaze counts every download and every read
request against a daily cap on the free tier, and one song is dozens of small segment requests, so
without a cache the cap runs out quickly and playback stops.

Live at `https://shadow-listens-cdn.shadow-listens.workers.dev` (free `workers.dev` address, no domain).

## How it works

- The stream service keeps issuing the same signed links (`/hls/<token>/...`, `/cover/<token>`). Only
  the host in front of them changes (`STREAM_PUBLIC_PREFIX`, below).
- `default` entrypoint, never cached: verifies the link with the same HMAC secret as the stream service
  (`src/token.ts`, tested against tokens minted by the Python signer), checks the path against the same
  whitelist, then forwards a token-free internal path to `Storage`.
- `Storage` entrypoint, cached by Cloudflare's Workers Caching: keyed by path only, so every listener and
  every token shares one copy. On a miss it reads B2 with a signed S3 request. Files are immutable (a new
  upload gets a new track id), so they are cached for a year (playlists one hour, covers one day).
- Failures are never cached. A Backblaze 403 (cap exceeded) is reported as 503 so players retry.
- The Cache API does not work on `workers.dev`; Workers Caching (the `[cache]` block in `wrangler.toml`)
  does. This was verified on this account: first request `Cf-Cache-Status: MISS`, then `HIT` for other tokens.

## Secrets and config

`wrangler.toml` holds the non-secret config (endpoint, region, bucket names, allowed origins). Secrets:

```
cd cdn
npx wrangler secret put STREAM_SIGNING_SECRET   # must equal the stream service's value on Render
npx wrangler secret put S3_ACCESS_KEY           # Backblaze application key (read access is enough)
npx wrangler secret put S3_SECRET_KEY
```

The signing secret must match what Render's services use. A value that does not match shows up as
`403 Invalid or expired link` for every real playback link.

## Deploy

```
cd cdn && npm install && npx wrangler deploy
```

## Switching playback onto it (and back)

Set `STREAM_PUBLIC_PREFIX=https://shadow-listens-cdn.shadow-listens.workers.dev` on BOTH the
`shadow-listens-stream` and `shadow-listens-catalogue` Render services (stream issues audio links,
catalogue issues cover links), then let them redeploy. To roll back, delete the variable (the default is
`/api/stream`, the Render route) and redeploy. No code change is needed either way.

## Checking it works

```
curl -sI -H "Origin: https://shadow-listens.shadow-listens.workers.dev" "<worker url>/hls/<token>/master.m3u8"
```

`Cf-Cache-Status: MISS` the first time, `HIT` after. Hits do not touch Backblaze at all.

## Verifying the deployed Worker against real Backblaze

```
set -a; source .env.prod; set +a; export PYTHONUTF8=1
.venv/Scripts/python cdn/test/verify_live.py
```

Picks a real ready track, signs links with the production secret, and checks master/variant/segment/cover, CORS, the forged-link refusal, and that the second read is a cache `HIT` (also for a different user's link). Exit code 2 means Backblaze is still refusing reads (daily cap), 0 means everything passed.

## Tests

```
npm test                                      # token verification vs. the Python signer
.venv/Scripts/python cdn/test/e2e_local.py    # runs the Worker locally against a mock S3
```

The end-to-end script checks routing, signed storage reads, headers, CORS and every refusal case. Its
last two checks (served from cache after storage loses the file) need Cloudflare's network, because local
`wrangler dev` does not emulate Workers Caching; they are expected to fail locally.

If the token format in `libs/common/listens_common/signing.py` ever changes, regenerate
`test/fixtures.json` with the real signer and update `src/token.ts` to match.
