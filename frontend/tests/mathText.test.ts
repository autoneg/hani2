// Run with `npm test` (node --test; Node strips the TypeScript types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { placeholderTex, protectMath, splitMath } from "../src/ui/mathText.ts";

const maths = (s: string) => splitMath(s).filter((p) => p.kind === "math");

test("inline and display math", () => {
  assert.deepEqual(maths("utility $u_h(\\omega)$ of"), [{ kind: "math", tex: "u_h(\\omega)", display: false }]);
  assert.deepEqual(maths("so\n\n$$\n\\frac{a}{b}\n$$\n\nend"), [{ kind: "math", tex: "\\frac{a}{b}", display: true }]);
  assert.deepEqual(maths("inline $$x^2$$ too"), [{ kind: "math", tex: "x^2", display: true }]);
  assert.equal(maths("$a$ and $b$").length, 2);
});

test("prices and other dollars stay text", () => {
  for (const s of ["a $5 price", "between $5 and $10", "$5-$10", "costs $ 5 or $6", "only \\$x\\$ here", "a lone $", "$ x$", "$x $"])
    assert.deepEqual(maths(s), [], s);
  assert.equal(splitMath("between $5 and $10").map((p) => (p.kind === "text" ? p.text : "")).join(""), "between $5 and $10");
});

test("math does not cross a blank line", () => {
  assert.deepEqual(maths("$a\n\nb$"), []);
  assert.equal(maths("$a\nb$").length, 1);
});

test("code is left alone", () => {
  assert.deepEqual(maths("`$x$` and ``a ` $y$``"), []);
  const md = "text $x$\n\n```\n$y$\n```\n";
  const out = protectMath(md);
  assert.ok(out.includes("```\n$y$\n```"));
  assert.ok(!out.includes("$x$"));
});

test("placeholders round-trip", () => {
  const out = protectMath("a $\\lvert x \\rvert$ b");
  const code = /`([^`]*)`/.exec(out)![1];
  assert.deepEqual(placeholderTex(code), { tex: "\\lvert x \\rvert", display: false });
  assert.equal(placeholderTex("plain code"), null);
});
