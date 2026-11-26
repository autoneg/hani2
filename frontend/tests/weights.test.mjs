// The score builder's weights: the running sum, Save only at 100 %, Normalise, % ↔ fractions.
import assert from "node:assert/strict";
import { test } from "node:test";
import { atHundred, normalise, sumPercent, sumText, toFractions, toPercent } from "../src/admin/weights.ts";

const close = (a, b, eps = 1e-12) => Math.abs(a - b) <= eps;

test("the running sum ignores empty and negative weights", () => {
  assert.equal(sumPercent([30, 20, "", null, 50]), 100);
  assert.equal(sumPercent([-5, 10]), 10);
  assert.equal(sumText([33.333, 33.333]), "66.67 %");
});

test("Save only at 100 %", () => {
  assert.ok(atHundred([30, 70]));
  assert.ok(atHundred([33.33333, 33.33333, 33.33334]));
  assert.ok(!atHundred([33.33, 33.33, 33.33]), "99.99 % is not 100 %");
  assert.ok(!atHundred([50, 51]));
  assert.ok(!atHundred([-10, 110]), "negative weights are refused");
  assert.ok(!atHundred([]));
});

test("Normalise keeps proportions and sums to exactly 100", () => {
  assert.deepEqual(normalise([1, 1, 1]), [33.34, 33.33, 33.33]);
  assert.deepEqual(normalise([30, 10]), [75, 25]);
  for (const ws of [[1, 1, 1], [7, 3, 9, 2, 1], [0.1, 0.2], [40, 40, 40, 40, 40, 40, 40]]) {
    const n = normalise(ws);
    assert.equal(Math.round(n.reduce((a, b) => a + b, 0) * 100), 10000, String(ws));
    assert.ok(atHundred(n), String(ws));
  }
  assert.deepEqual(normalise([0, 0, 0, 0]), [25, 25, 25, 25], "all zero: equal shares");
  assert.deepEqual(normalise([0, 5]), [0, 100], "a zero weight stays 0");
  assert.deepEqual(normalise([]), []);
  // a stored score whose fractions are thirds opens at exactly 100 %, so it can be saved again
  assert.ok(atHundred(normalise([1 / 3, 1 / 3, 1 / 3])));
  assert.ok(atHundred(normalise([1 / 7, 2 / 7, 4 / 7])));
});

test("percentages are saved as fractions that sum to 1 (within the API's 1e-6)", () => {
  const f = toFractions([33.34, 33.33, 33.33]);
  assert.ok(Math.abs(f.reduce((a, b) => a + b, 0) - 1) < 1e-6);
  assert.ok(close(toFractions([30, 70])[0], 0.3));
  assert.deepEqual(toPercent([0.3, 0.7]), [30, 70]);
  assert.deepEqual(toPercent([1 / 3]), [33.33]);
});
