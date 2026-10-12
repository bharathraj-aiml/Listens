import assert from "node:assert/strict";
import { test } from "node:test";
import worker, { routeFor, rewriteLocation, UPSTREAMS } from "./cloudflare-worker.js";

test("API prefixes go to their service with the prefix removed, like the nginx gateway", () => {
  assert.deepEqual(routeFor("/api/auth/login"), { name: "auth", path: "/login" });
  assert.deepEqual(routeFor("/api/catalogue/tracks/abc/similar"), { name: "catalogue", path: "/tracks/abc/similar" });
  assert.deepEqual(routeFor("/api/catalogue/upload"), { name: "catalogue", path: "/upload" });
  assert.deepEqual(routeFor("/api/stream/tracks/x/url"), { name: "stream", path: "/tracks/x/url" });
});

test("everything else goes to the frontend unchanged", () => {
  for (const p of ["/", "/login", "/albums", "/_next/static/chunks/a.js", "/api", "/api/", "/api/other/x", "/api/authx/y"]) {
    assert.deepEqual(routeFor(p), { name: "frontend", path: p }, p);
  }
});

test("redirects to a service's own address are pointed back at the site", () => {
  const site = "https://shadow-listens.shadow-listens.workers.dev";
  assert.equal(rewriteLocation(UPSTREAMS.frontend + "/login?next=%2F", site), site + "/login?next=%2F");
  assert.equal(rewriteLocation(UPSTREAMS.auth, site), site);
  assert.equal(rewriteLocation("/albums", site), "/albums");
  assert.equal(rewriteLocation("https://example.com/x", site), "https://example.com/x");
  assert.equal(rewriteLocation(UPSTREAMS.frontend + "evil.example/x", site), UPSTREAMS.frontend + "evil.example/x");
  assert.equal(rewriteLocation(null, site), null);
});

function run(request, responses) {
  const calls = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (req) => {
    calls.push(new Request(req).url);
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  const waits = [];
  const ctx = { waitUntil: (p) => waits.push(p) };
  return worker.fetch(request, {}, ctx).then(async (res) => { await Promise.all(waits); return { res, calls }; }).finally(() => { globalThis.fetch = realFetch; });
}
const site = "https://shadow-listens.shadow-listens.workers.dev";

test("a request is forwarded to the right service with the query string", async () => {
  const { res, calls } = await run(new Request(site + "/api/catalogue/tracks?limit=5"), [new Response("[]")]);
  assert.equal(res.status, 200);
  assert.deepEqual(calls, [UPSTREAMS.catalogue + "/tracks?limit=5"]);
});

test("entry pages also wake the API services, other pages do not", async () => {
  const html = { headers: { accept: "text/html" } };
  const entry = await run(new Request(site + "/login", html), [new Response("page"), new Response("ok"), new Response("ok"), new Response("ok")]);
  assert.equal(entry.calls.length, 4);
  assert.ok(entry.calls.includes(UPSTREAMS.auth + "/health") && entry.calls.includes(UPSTREAMS.stream + "/health"));
  const inner = await run(new Request(site + "/albums", html), [new Response("page")]);
  assert.deepEqual(inner.calls, [UPSTREAMS.frontend + "/albums"]);
  const api = await run(new Request(site + "/", { headers: { accept: "application/json" } }), [new Response("x")]);
  assert.equal(api.calls.length, 1);
});

test("a redirect from a service is rewritten to the site address", async () => {
  const { res } = await run(new Request(site + "/profile"), [new Response(null, { status: 308, headers: { Location: UPSTREAMS.frontend + "/profile/" } })]);
  assert.equal(res.headers.get("Location"), site + "/profile/");
});

test("a GET that gets 502 is retried and the success is returned", async () => {
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn) => realSetTimeout(fn, 0); // do not actually wait 4 s per retry in the test
  try {
    const { res, calls } = await run(new Request(site + "/albums"), [new Response("bad", { status: 502 }), new Response("bad", { status: 503 }), new Response("fine")]);
    assert.equal(await res.text(), "fine");
    assert.equal(calls.length, 3);
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
});

test("after the retries are used up the last answer is passed through", async () => {
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn) => realSetTimeout(fn, 0);
  try {
    const { res, calls } = await run(new Request(site + "/albums"), [new Response("a", { status: 502 }), new Response("b", { status: 502 }), new Response("c", { status: 502 })]);
    assert.equal(res.status, 502);
    assert.equal(calls.length, 3);
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
});

test("a POST is never retried, even on 502", async () => {
  const { res, calls } = await run(new Request(site + "/api/auth/login", { method: "POST", body: "{}" }), [new Response("bad", { status: 502 })]);
  assert.equal(res.status, 502);
  assert.equal(calls.length, 1);
});

test("a network failure on a POST gives a friendly 503, not a crash", async () => {
  const { res } = await run(new Request(site + "/api/auth/login", { method: "POST", body: "{}" }), [new Error("connection reset")]);
  assert.equal(res.status, 503);
  assert.match(await res.text(), /starting up/);
});

test("/healthz answers without touching any service", async () => {
  const { res, calls } = await run(new Request(site + "/healthz"), []);
  assert.equal(await res.text(), "ok\n");
  assert.equal(calls.length, 0);
});
