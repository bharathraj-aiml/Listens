/** Shadow Listens CDN: Cloudflare's cache in front of the private Backblaze B2 buckets.
 *
 * The browser asks this Worker for HLS segments and covers instead of going through the Render
 * stream service. Backblaze charges (and, on the free tier, hard-caps) every download and every
 * read request, and one song is dozens of small segment requests, so serving repeats from
 * Cloudflare's cache keeps both numbers close to zero. A file is fetched from Backblaze once.
 *
 * Two entrypoints (see wrangler.toml, this is Cloudflare's "authenticated responses" pattern):
 *
 *   default  runs on EVERY request and is never cached: checks the signed link (the same HMAC
 *            tokens the stream service issues), then forwards a token-free internal URL.
 *   Storage  cached: keyed by that internal path only ("/hls/<track>/<file>"), so every listener
 *            and every token shares one copy. On a miss it reads Backblaze with a signed S3 request.
 *
 * Because the check happens before the cache, an expired or forged link never receives cached
 * bytes. The files are immutable (new upload = new track id), so they cache for a year. */
import { WorkerEntrypoint } from "cloudflare:workers";
import { AwsClient } from "aws4fetch";
import { verifyToken } from "./token.ts";

export interface Env {
  STREAM_SIGNING_SECRET: string;
  S3_ACCESS_KEY: string;
  S3_SECRET_KEY: string;
  S3_ENDPOINT_URL: string;
  S3_REGION: string;
  S3_BUCKET_AUDIO: string;
  S3_BUCKET_COVERS: string;
  ALLOWED_ORIGINS: string;
}

// Only the file shapes the transcoder produces; also rules out path traversal by construction.
// Same whitelist as services/stream/app/main.py.
const HLS_PATH = /^(master\.m3u8|q\d{2,3}\/(index\.m3u8|seg_\d{3,5}\.ts))$/;
const INTERNAL_HOST = "https://storage.internal";

const CONTENT_TYPE: Record<string, string> = { m3u8: "application/vnd.apple.mpegurl", ts: "video/mp2t", jpg: "image/jpeg" };
const CACHE_CONTROL = {
  segment: "public, max-age=31536000, immutable",
  playlist: "public, max-age=3600",
  cover: "public, max-age=86400",
};

function corsHeaders(request: Request, env: Env): Record<string, string> {
  const origin = request.headers.get("Origin");
  const allowed = env.ALLOWED_ORIGINS.split(",").map((o) => o.trim()).filter(Boolean);
  const headers: Record<string, string> = { Vary: "Origin" };
  if (origin && allowed.includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Range, Content-Type";
    headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Type";
    headers["Access-Control-Max-Age"] = "86400";
  }
  return headers;
}

function reply(request: Request, env: Env, status: number, body: BodyInit | null, extra: Record<string, string> = {}): Response {
  return new Response(body, { status, headers: { "X-Content-Type-Options": "nosniff", ...extra, ...corsHeaders(request, env) } });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return reply(request, env, 204, null);
    if (request.method !== "GET" && request.method !== "HEAD") return reply(request, env, 405, "Method not allowed", { Allow: "GET, HEAD, OPTIONS" });

    const url = new URL(request.url);
    if (url.pathname === "/health") return reply(request, env, 200, "ok", { "Cache-Control": "no-store" });

    const hls = url.pathname.match(/^\/hls\/([^/]+)\/(.+)$/);
    const cover = url.pathname.match(/^\/cover\/([^/]+)$/);
    let internal: string | null = null;

    if (hls) {
      const trackId = await verifyToken(env.STREAM_SIGNING_SECRET, hls[1], "hls");
      if (!trackId) return reply(request, env, 403, "Invalid or expired link", { "Cache-Control": "no-store" });
      if (!HLS_PATH.test(hls[2])) return reply(request, env, 404, "Not found", { "Cache-Control": "no-store" });
      internal = `${INTERNAL_HOST}/hls/${trackId}/${hls[2]}`;
    } else if (cover) {
      const trackId = await verifyToken(env.STREAM_SIGNING_SECRET, cover[1], "cover");
      if (!trackId) return reply(request, env, 403, "Invalid or expired link", { "Cache-Control": "no-store" });
      internal = `${INTERNAL_HOST}/cover/${trackId}`;
    }
    if (!internal) return reply(request, env, 404, "Not found", { "Cache-Control": "no-store" });

    // A fresh GET with no Range, no cookies and no Authorization: only the path decides the cache key.
    const upstream = await ctx.exports.Storage.fetch(new Request(internal, { method: "GET" }));
    const out = new Response(upstream.body, upstream);
    for (const [k, v] of Object.entries({ "X-Content-Type-Options": "nosniff", ...corsHeaders(request, env) })) out.headers.set(k, v);
    return out;
  },
} satisfies ExportedHandler<Env>;

export class Storage extends WorkerEntrypoint<Env> {
  async fetch(request: Request): Promise<Response> {
    const env = this.env;
    const parts = new URL(request.url).pathname.split("/").filter(Boolean); // ["hls", id, ...file] | ["cover", id]
    const isCover = parts[0] === "cover";
    const bucket = isCover ? env.S3_BUCKET_COVERS : env.S3_BUCKET_AUDIO;
    const key = isCover ? `tracks/${parts[1]}.jpg` : `hls/${parts[1]}/${parts.slice(2).join("/")}`;
    const ext = key.slice(key.lastIndexOf(".") + 1);

    const aws = new AwsClient({ accessKeyId: env.S3_ACCESS_KEY, secretAccessKey: env.S3_SECRET_KEY, region: env.S3_REGION, service: "s3" });
    const res = await aws.fetch(`${env.S3_ENDPOINT_URL}/${bucket}/${key}`);

    if (res.status === 200) {
      const cacheControl = isCover ? CACHE_CONTROL.cover : ext === "ts" ? CACHE_CONTROL.segment : CACHE_CONTROL.playlist;
      return new Response(res.body, {
        status: 200,
        headers: {
          "Content-Type": CONTENT_TYPE[ext] ?? "application/octet-stream",
          "Cache-Control": cacheControl,
          ...(res.headers.get("Content-Length") ? { "Content-Length": res.headers.get("Content-Length")! } : {}),
        },
      });
    }
    // Never cache a failure. Backblaze answers 403 when a daily cap is exceeded, which is a temporary
    // problem on our side rather than "no such file", so it is reported as 503 and players retry.
    const status = res.status === 404 ? 404 : 503;
    return new Response(status === 404 ? "Not found" : "Storage temporarily unavailable", { status, headers: { "Cache-Control": "no-store" } });
  }
}
