// What each mode offers in the editor: the human entries of the opponent pool, the pairing defaults and
// how a match is formed (§4.2), which scheduling dimensions are used, and the live mode that falls
// back to the env.json pool.
import assert from "node:assert/strict";
import { test } from "node:test";
import { allowedHumans, assignOptions, liveMode, pairingDefaults, poolEntryProblem, poolOffers, schedulingUse } from "../src/admin/modes.ts";

test("Paired offers only the human entry of the right kind, Solo none, Mixed and undeclared all", () => {
  assert.deepEqual(allowedHumans("paired", "assistant"), ["human+assistant"]);
  assert.deepEqual(allowedHumans("paired", "opponent"), ["human"]);
  assert.deepEqual(allowedHumans("paired", "none"), ["human", "human+assistant"]);
  assert.deepEqual(allowedHumans("solo", "assistant"), []);
  assert.equal(allowedHumans("mixed", "assistant"), null);
  assert.equal(allowedHumans(null, "assistant"), null);
  assert.ok(poolOffers("human+assistant", "paired", "assistant"));
  assert.ok(!poolOffers("human", "paired", "assistant"));
  assert.ok(!poolOffers(":pan", "paired", "assistant"), "a Paired pool lists people only");
  assert.ok(poolOffers("human", "paired", "opponent"));
  assert.ok(!poolOffers("Human + Assistant", "paired", "opponent"));
  assert.ok(!poolOffers("human", "solo", "none"));
  assert.ok(poolOffers(":pan", "solo", "assistant"));
  assert.ok(poolOffers("human", null, "assistant") && poolOffers(":pan", "mixed", "assistant"));
  assert.match(poolEntryProblem("human", "solo", "assistant"), /AI opponents only/);
});

test("the pairing defaults and how a match is formed follow the mode", () => {
  assert.equal(pairingDefaults("paired", true).assign, "cells");
  assert.equal(pairingDefaults("paired", true).scope, "study");
  assert.equal(pairingDefaults("paired", false).assign, "random", "only a declared Paired study");
  assert.equal(pairingDefaults("mixed", true).assign, "random");
  assert.equal(assignOptions("paired")[0].value, "cells");
  assert.equal(assignOptions("mixed")[0].value, "random");
  assert.deepEqual(assignOptions("paired").map((o) => o.value).sort(), ["cells", "order", "random"]);
});

test("Paired uses no opponent method and no crossing; a Paired HAN study no Assistant method", () => {
  const hi = schedulingUse("paired", "assistant");
  assert.ok(hi.opponents && hi.cross && !hi.assistants && hi.assistantsHint);
  assert.ok(schedulingUse("paired", "opponent").assistants);
  const solo = schedulingUse("solo", "assistant");
  assert.ok(!solo.opponents && !solo.cross && !solo.assistants);
});

test("the live mode falls back to the env.json pool when no file names one", () => {
  const ed = { kind: "assistant", inherited: {}, pools: { opponents: { env: ["human+assistant"] } } };
  const m = liveMode({}, ed);
  assert.equal(m.derived, "paired");
  assert.ok(m.fromEnv);
  assert.equal(liveMode({ opponents: [":pan"] }, ed).derived, "solo", "the file wins");
  assert.equal(liveMode({}, { ...ed, inherited: { opponents: ["human", ":pan"] } }).derived, "mixed", "then the project");
  assert.equal(liveMode({ study_mode: "solo" }, ed).mode, "solo");
  assert.deepEqual(liveMode({}, { inherited: { assistants: ["x.A"] } }).assistants, ["x.A"]);
});
