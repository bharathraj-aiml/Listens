import assert from "node:assert/strict";
import { test } from "node:test";
import { creditOf, creditText, sharesArtist } from "./credit.ts";

const ref = (id: string, name: string) => ({ id, name });

test("a track with no artists list falls back to its primary artist", () => {
  const t = { artist: ref("a", "Mano") };
  assert.deepEqual(creditOf(t), [ref("a", "Mano")]);
  assert.equal(creditText(t), "Mano");
});

test("the credit lists everyone in order", () => {
  const t = { artist: ref("a", "Yuvan"), artists: [ref("a", "Yuvan"), ref("b", "Na.Muthukumar")] };
  assert.equal(creditText(t), "Yuvan, Na.Muthukumar");
});

test("tracks share an artist when any credited person overlaps, not only the primary", () => {
  const duet = { artist: ref("a", "A"), artists: [ref("a", "A"), ref("b", "B")] };
  const bSolo = { artist: ref("b", "B") };
  const other = { artist: ref("c", "C") };
  assert.equal(sharesArtist(duet, bSolo), true);
  assert.equal(sharesArtist(duet, other), false);
});
