// Every editor choice that is not self-explanatory (help_texts.REQUIRED) has its `?` in the editor,
// and rows find their help text by key or id. The mode, HAN and K-of-N helpers of the editor.
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { resolveHelp } from "../src/admin/helpKeys.ts";
import { derive, hanToken, hanYearLabel, hanYears, kOfN, modeProblems } from "../src/admin/modes.ts";

const here = new URL(".", import.meta.url).pathname;
const py = readFileSync(join(here, "../../src/hani2/help_texts.py"), "utf8");

function required() {
  const m = /^REQUIRED = \(([\s\S]*?)^\)/m.exec(py);
  assert.ok(m, "REQUIRED = (...) not found in help_texts.py");
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

function sources(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? sources(p) : /\.tsx?$/.test(f) ? [readFileSync(p, "utf8")] : [];
  });
}

test("every required id occurs in the editor's sources", () => {
  const ids = required();
  assert.ok(ids.length > 20);
  const src = sources(join(here, "../src/admin")).join("\n");
  const missing = ids.filter((id) => !src.includes(`"${id}"`));
  assert.deepEqual(missing, [], "give these rows help=\"<id>\"");
});

test("a row finds its text by help key, by id, or by id with dashes", () => {
  const t = { "pairing.assign": { title: "How" }, study_mode: { title: "Mode" } };
  assert.equal(resolveHelp("pairing.assign", undefined, t)?.title, "How");
  assert.equal(resolveHelp(undefined, "pairing-assign", t)?.title, "How");
  assert.equal(resolveHelp(undefined, "study_mode", t)?.title, "Mode");
  assert.equal(resolveHelp({ title: "Inline" }, "study_mode", t)?.title, "Inline");
  assert.equal(resolveHelp(undefined, "nothing", t), null);
  assert.equal(resolveHelp("study_mode", undefined, null), null, "texts not loaded yet");
});

test("the derived mode and the checks against the pool", () => {
  assert.equal(derive(undefined), "solo");
  assert.equal(derive([":pan"]), "solo");
  assert.equal(derive(["Human + Assistant"]), "paired");
  assert.equal(derive("human, :pan"), "mixed");
  assert.deepEqual(modeProblems(null, ["human"], [], "assistant"), []);
  assert.equal(modeProblems("solo", ["human", ":pan"], [], "none").length, 1);
  assert.deepEqual(modeProblems("paired", ["human+assistant"], [], "assistant"), []);
  assert.equal(modeProblems("paired", ["human"], [], "assistant").length, 1);
  assert.deepEqual(modeProblems("paired", [], [], "opponent"), [], "filled in by the server");
  assert.equal(modeProblems("paired", [], ["x.Y"], "opponent").length, 1);
  assert.equal(modeProblems("mixed", [], [], "none").length, 1);
  assert.equal(modeProblems("mixed", [":pan"], [], "none").length, 1);
  assert.deepEqual(modeProblems("mixed", ["human", ":pan"], [], "none"), []);
});

test("HAN years: labels from the project's year, uncovered years greyed out", () => {
  assert.deepEqual(hanToken(":han2026-finalists"), { year: 2026, set: "finalists" });
  assert.equal(hanToken(":pan"), null);
  const ys = hanYears(2027, [2026], 2027);
  assert.deepEqual(ys.map((y) => [y.year, y.relative, y.covered, y.source]), [[2027, "this year", true, "submissions"], [2026, "last year", true, "han-agents"]]);
  const old = hanYears(2026, [2026], null);
  assert.deepEqual(old.map((y) => [y.year, y.relative, y.covered]), [[2026, "this year", true], [2025, "last year", false]]);
  assert.equal(hanYearLabel(old[1]), "2025 (last year): no agents for 2025");
  assert.deepEqual(hanYears(null, [2026], null).map((y) => y.relative), [""], "no project year: no labels");
});

test("K versus N", () => {
  assert.ok(kOfN("latin_square", 6, 5).warn);
  assert.ok(!kOfN("latin_square", 5, 5).warn);
  assert.match(kOfN("latin_square", 5, 5).text, /every Assistant once/);
  assert.ok(!kOfN("balanced", 6, 5).warn, "one Assistant per person");
  assert.ok(!kOfN("random_each", 6, 5).warn);
  assert.ok(!kOfN("cyclic", 6, null).warn, "unknown N: no warning");
});
