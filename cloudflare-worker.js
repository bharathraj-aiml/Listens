// Shadow Listens - the site Worker (https://shadow-listens.shadow-listens.workers.dev).
//
// It is the front door and does the gateway's job itself: /api/auth, /api/catalogue and /api/stream go to
// those services and everything else to the frontend, exactly like gateway/nginx.render.conf.template.
//
// Why not just forward to the Render gateway (the earlier design)? Render's free services sleep after ~15
// idle minutes. A request from OUTSIDE Render to a sleeping service is held for ~20-30 s while it wakes and
// then succeeds. The gateway runs INSIDE Render, and its hop to a sleeping sibling is answered with an
// instant "502 Bad Gateway" instead (measured: the same request made from outside waited 23 s and worked).
// So the first visit after any idle spell showed a 502 until something else woke the services. Calling the
// services directly from here removes that hop. Nothing here runs on a schedule, so it costs no Render hours
// beyond the services actually being used.
//
// Also: on an entry page (/, /login, /register) the other services are pinged in parallel so they wake while
// the page loads rather than one after another once the app starts calling them, and a GET that still gets
// 502/503/504 (a service mid-wake or mid-deploy) is retried a couple of times. Non-GET requests are never
// retried (their body cannot be replayed).
//
// Known limit (free plan): Cloudflare caps request bodies at 100 MB, below the app's 500 MB upload setting.
// Uploads over 100 MB fail through this address.

export const UPSTREAMS = {
  frontend: "https://shadow-listens-frontend.onrender.com",
  auth: "https://shadow-listens-auth.onrender.com",
  catalogue: "https://shadow-listens-catalogue.onrender.com",
  stream: "https://shadow-listens-stream.onrender.com",
};

const API_SERVICES = ["auth", "catalogue", "stream"];
const ENTRY_PAGES = new Set(["/", "/login", "/register"]);
const RETRYABLE = new Set([502, 503, 504]);
const RETRIES = 2;
const RETRY_DELAY_MS = 4000;

/** Which service handles this path, and the path to ask it for: "/api/auth/login" -> auth "/login". */
export function routeFor(pathname) {
  for (const name of API_SERVICES) {
    const prefix = `/api/${name}/`;
    if (pathname.startsWith(prefix)) return { name, path: "/" + pathname.slice(prefix.length) };
  }
  return { name: "frontend", path: pathname };
}

/** Point a redirect back at this site instead of at the service's own *.onrender.com address. */
export function rewriteLocation(location, siteOrigin) {
  if (!location) return location;
  for (const base of Object.values(UPSTREAMS)) {
    if (location === base || location.startsWith(base + "/") || location.startsWith(base + "?")) return siteOrigin + location.slice(base.length);
  }
  return location;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchService(url, request) {
  const replayable = request.method === "GET" || request.method === "HEAD";
  for (let attempt = 0; ; attempt++) {
    let res = null;
    try {
      res = await fetch(new Request(url, request));
    } catch (err) {
      if (!replayable || attempt >= RETRIES) throw err;
    }
    if (res && (!replayable || !RETRYABLE.has(res.status) || attempt >= RETRIES)) return res;
    await sleep(RETRY_DELAY_MS);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") return new Response("ok\n", { headers: { "Cache-Control": "no-store" } });

    const { name, path } = routeFor(url.pathname);

    if (request.method === "GET" && ENTRY_PAGES.has(url.pathname) && (request.headers.get("accept") || "").includes("text/html")) {
      // wake the API services while the page itself loads (a no-op for any that are already awake)
      for (const svc of API_SERVICES) ctx.waitUntil(fetch(`${UPSTREAMS[svc]}/health`).catch(() => {}));
    }

    let res;
    try {
      res = await fetchService(UPSTREAMS[name] + path + url.search, request);
    } catch {
      return new Response("The server is starting up. Please try again in a moment.", { status: 503, headers: { "Retry-After": "10", "Cache-Control": "no-store" } });
    }
    const out = new Response(res.body, res);
    const location = out.headers.get("Location");
    if (location) out.headers.set("Location", rewriteLocation(location, url.origin));
    return out;
  },
};
