import assert from "node:assert/strict";
import { test } from "node:test";
import { longestWait, SLOW_MS } from "./net.ts";

test("nothing pending means no wait", () => {
  assert.equal(longestWait([], 10_000), 0);
});

test("the wait is measured from the OLDEST pending request", () => {
  assert.equal(longestWait([9_000, 4_000, 9_500], 10_000), 6_000);
});

test("a clock that moved backwards never gives a negative wait", () => {
  assert.equal(longestWait([12_000], 10_000), 0);
});

test("only waits past the slow threshold should trigger the banner", () => {
  assert.ok(longestWait([1_000], 3_500) < SLOW_MS);
  assert.ok(longestWait([1_000], 4_100) >= SLOW_MS);
});
