// Shadow Listens - Cloudflare Worker reverse proxy in front of the Render gateway.
//
// Why this exists: Cloudflare's CDN can't front a custom domain we don't own, and a free
// *.onrender.com subdomain can't be put behind Cloudflare either (Cloudflare needs to be
// authoritative DNS for whatever's in front, and we don't own onrender.com). A Worker sidesteps
// both problems - it gets its own free *.workers.dev subdomain automatically, runs on
// Cloudflare's edge (including PoPs near India), and can proxy to any origin over the internet.
//
// Caching: this relies entirely on the origin's own Cache-Control headers (already set
// correctly by services/worker/app/jobs.py and services/stream/app/main.py - immutable/1yr for
// HLS segments, 1hr revalidate for playlists, 1 day for covers) rather than forcing
// cacheEverything - auth/catalogue responses must never be cached, and trusting Cache-Control
// is what keeps that distinction correct automatically.
//
// Known limitation (free tier): Cloudflare Workers caps request bodies at 100MB, below this
// app's own MAX_UPLOAD_MB=500 setting. Uploads over 100MB will fail through this Worker's URL.
// Accepted tradeoff per user decision - most individual audio files are well under 100MB.

const ORIGIN = "https://shadow-listens-gateway.onrender.com";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const originUrl = ORIGIN + url.pathname + url.search;

    // Preserve method/headers/body from the original request; only the URL changes. The target
    // URL's own hostname is what determines the outbound Host header/TLS SNI - no need to set
    // it explicitly (Workers' fetch() may not even allow overriding it).
    const originRequest = new Request(originUrl, request);
    return fetch(originRequest);
  },
};
