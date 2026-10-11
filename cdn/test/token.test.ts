import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { verifyToken } from "../src/token.ts";

// Tokens minted by the real Python signer (libs/common/listens_common/signing.py), so a change on either
// side that breaks agreement fails here. Regenerate with the snippet in cdn/README.md if the format changes.
const fx = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));
const NOW = 4102444800 * 1000 - 1800 * 1000; // half an hour before the valid tokens expire

test("accepts a token signed by the Python side and returns the track id", async () => {
  assert.equal(await verifyToken(fx.secret, fx.hls, "hls", NOW), fx.trackId);
  assert.equal(await verifyToken(fx.secret, fx.cover, "cover", NOW), fx.trackId);
});

test("rejects the wrong kind: a cover link cannot open audio and vice versa", async () => {
  assert.equal(await verifyToken(fx.secret, fx.cover, "hls", NOW), null);
  assert.equal(await verifyToken(fx.secret, fx.hls, "cover", NOW), null);
});

test("rejects expired links", async () => {
  assert.equal(await verifyToken(fx.secret, fx.expired, "hls", NOW), null);
  assert.equal(await verifyToken(fx.secret, fx.hls, "hls", 4102444800 * 1000 + 1000), null);
});

test("rejects a token signed with a different secret", async () => {
  assert.equal(await verifyToken(fx.secret, fx.wrongSecret, "hls", NOW), null);
  assert.equal(await verifyToken("not-the-secret", fx.hls, "hls", NOW), null);
});

test("rejects tampering: edited payload, edited signature, truncation", async () => {
  const [body, mac] = fx.hls.split(".");
  const flipped = (s: string) => s.slice(0, -2) + (s.endsWith("A") ? "B" : "A") + s.slice(-1);
  assert.equal(await verifyToken(fx.secret, `${flipped(body)}.${mac}`, "hls", NOW), null);
  assert.equal(await verifyToken(fx.secret, `${body}.${flipped(mac)}`, "hls", NOW), null);
  assert.equal(await verifyToken(fx.secret, `${body}.${mac.slice(0, 10)}`, "hls", NOW), null);
});

test("rejects garbage without throwing", async () => {
  for (const junk of ["", ".", "abc", "a.b", "....", "%%%.%%%", "eyJ.eyJ"]) {
    assert.equal(await verifyToken(fx.secret, junk, "hls", NOW), null, junk);
  }
});
