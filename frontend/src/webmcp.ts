/**
 * WebMCP: expose the negotiation page to AI agents running in the browser.
 *
 * Uses `document.modelContext.registerTool()` (current draft) and falls back to
 * the older `navigator.modelContext`. Tools are unregistered with an
 * AbortSignal. Every tool call is logged on the server as a `webmcp` event, so
 * studies can tell when a browser agent acted.
 */
import { flushDraftText, useStore } from "./store";
import type { SessionState } from "./types";

type Json = any;
interface ToolDef {
  name: string;
  title: string;
  description: string;
  inputSchema: Json;
  action?: boolean; // changes the negotiation (only when actions are allowed)
  annotations?: Json;
  execute: (input: Json) => Promise<Json>;
}

const S = () => useStore.getState();
const st = () => S().state as SessionState | null;

function modelContext(): any {
  return (document as any).modelContext ?? (navigator as any).modelContext ?? null;
}

export function webmcpAvailable() {
  return !!modelContext();
}

function send(msg: Json) {
  S().send({ ...msg, via: "webmcp" });
}

function waitFor(pred: (s: SessionState) => boolean, timeout = 120000): Promise<SessionState> {
  return new Promise((resolve, reject) => {
    const now = st();
    if (now && pred(now)) return resolve(now);
    const t = window.setTimeout(() => {
      unsub();
      reject(new Error("timed out waiting for the negotiation to update"));
    }, timeout);
    const unsub = useStore.subscribe((s) => {
      if (s.state && pred(s.state)) {
        window.clearTimeout(t);
        unsub();
        resolve(s.state);
      }
    });
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function summary(s: SessionState) {
  const n = s.negotiation;
  return {
    phase: s.phase,
    round: s.round.label,
    scenario: s.scenario && {
      title: s.scenario.title,
      role: s.scenario.role,
      description: s.scenario.short_description,
      issues: s.scenario.issues,
    },
    is_my_turn: n.is_my_turn && !n.thinking,
    partner_is_thinking: n.thinking,
    step: n.step,
    n_steps: n.n_steps,
    seconds_left: n.deadline ? Math.max(0, Math.round(n.deadline - Date.now() / 1000)) : null,
    reserved_value: s.reserved_value,
    partner_offer: s.partner_offer && {
      outcome: s.partner_offer.values,
      text: s.partner_offer.text,
      utility_for_me: s.partner_offer.utility,
      message: s.partner_offer.message,
    },
    my_draft: { outcome: s.draft.values, message: s.draft.text, utility_for_me: s.draft.utility },
    history: s.history.slice(-12).map((h) =>
      h.kind === "system" ? { event: h.text } : { by: h.by === "human" ? "me" : "partner" /* wire name: kept for browser agents */, outcome: h.offer, message: h.text, utility_for_me: h.utility },
    ),
    result: s.result,
    questionnaire: s.phase === "questionnaire" ? s.questionnaire : null,
    tools: s.tools.filter((t) => t.visible).map((t) => ({ name: t.name, description: t.description, enabled: t.enabled })),
    assistant_available: !!s.support,
  };
}

const ok = (data: Json) => ({ content: [{ type: "text", text: JSON.stringify(data) }], ...(typeof data === "object" && data ? { structuredContent: data } : {}) });
const fail = (error: string) => ({ content: [{ type: "text", text: JSON.stringify({ ok: false, error }) }], isError: true });

async function afterTurn(prevLen: number) {
  // wait until our move is recorded and it is our turn again (or the negotiation ended)
  const s = await waitFor((x) => {
    if (!["running", "starting"].includes(x.phase)) return true;
    const offers = x.history.slice(prevLen).filter((h) => h.kind === "offer");
    const partnerReplied = offers.length > 0 && offers[offers.length - 1].by === "agent";
    return partnerReplied && x.negotiation.is_my_turn && !x.negotiation.thinking;
  });
  return summary(s);
}

function requireTurn(): string | null {
  const s = st();
  if (!s) return "The page is not connected yet.";
  if (s.phase !== "running") return `There is no running negotiation (phase: ${s.phase}). Call start_negotiation first.`;
  if (!s.negotiation.is_my_turn || s.negotiation.thinking) return "It is not your turn; the opponent is still thinking.";
  return null;
}

function toolDefs(): ToolDef[] {
  return [
    {
      name: "get_negotiation_state",
      title: "Get the negotiation state",
      description:
        "Everything visible on the page: the scenario and its issues, whose turn it is, the opponent's current offer and what it is worth to me (utility 0..1), my draft offer, my value on disagreement (reserved_value), recent history, time left and the result when finished.",
      inputSchema: { type: "object", properties: {} },
      annotations: { readOnlyHint: true },
      execute: async () => {
        const s = st();
        return s ? ok(summary(s)) : fail("The page is not connected yet.");
      },
    },
    {
      name: "evaluate_offer",
      title: "Evaluate an offer",
      description: "Put an outcome (issue name → value) in my offer editor without sending it, and return what it is worth to me.",
      inputSchema: { type: "object", properties: { outcome: { type: "object", description: "Issue name → value" } }, required: ["outcome"] },
      action: true,
      execute: async ({ outcome }) => {
        const before = st()?.draft.utility;
        send({ type: "draft", values: outcome });
        await Promise.race([waitFor((x) => Object.entries(outcome || {}).every(([k, v]) => String(x.draft.values[k]) === String(v)), 4000).catch(() => null), sleep(4000)]);
        const s = st()!;
        return ok({ outcome: s.draft.values, utility_for_me: s.draft.utility, previous_utility: before, reserved_value: s.reserved_value });
      },
    },
    {
      name: "start_negotiation",
      title: "Start the negotiation",
      description: "Start the negotiation with the scenario that is loaded (call load_next_scenario first after a negotiation ended). Waits for the opponent's first move.",
      inputSchema: { type: "object", properties: {} },
      action: true,
      execute: async () => {
        const s = st();
        if (!s) return fail("The page is not connected yet.");
        if (s.phase !== "ready") return fail(`Cannot start now (phase: ${s.phase}).`);
        send({ type: "start" });
        const x = await waitFor((y) => y.phase !== "ready" && y.phase !== "starting" && (!y.negotiation.thinking || y.phase !== "running"));
        return ok(summary(x));
      },
    },
    {
      name: "load_next_scenario",
      title: "Load the next scenario",
      description: "After a negotiation ended, load the next scenario so a new negotiation can start.",
      inputSchema: { type: "object", properties: {} },
      action: true,
      execute: async () => {
        const s = st();
        if (!s) return fail("The page is not connected yet.");
        if (!["ready", "ended"].includes(s.phase)) return fail(`Cannot load now (phase: ${s.phase}).`);
        send({ type: "load" });
        const x = await waitFor((y) => y.phase === "ready" && (s.phase !== "ready" || y.scenario?.name !== s.scenario?.name), 8000).catch(() => st()!);
        return ok(summary(x));
      },
    },
    {
      name: "send_counter_offer",
      title: "Send a counter-offer",
      description:
        "Reject the opponent's offer and send my counter-offer: an outcome (issue name → value, every issue) and an optional message to the opponent. Waits for the opponent's reply and returns the new state.",
      inputSchema: {
        type: "object",
        properties: { outcome: { type: "object", description: "Issue name → value for every issue" }, message: { type: "string" } },
        required: ["outcome"],
      },
      action: true,
      annotations: { consequentialHint: true },
      execute: async ({ outcome, message }) => {
        const err = requireTurn();
        if (err) return fail(err);
        const n = st()!.history.length;
        send({ type: "send", values: outcome, text: message ?? "" });
        return ok(await afterTurn(n));
      },
    },
    {
      name: "accept_offer",
      title: "Accept the opponent's offer",
      description: "Accept the offer on the table. This ends the negotiation with an agreement.",
      inputSchema: { type: "object", properties: {} },
      action: true,
      annotations: { consequentialHint: true },
      execute: async () => {
        const err = requireTurn();
        if (err) return fail(err);
        if (!st()!.partner_offer) return fail("There is no offer on the table to accept.");
        send({ type: "accept" });
        const x = await waitFor((y) => y.phase !== "running");
        return ok(summary(x));
      },
    },
    {
      name: "end_negotiation",
      title: "End the negotiation",
      description: "End the negotiation without agreement; I receive my value on disagreement (reserved_value).",
      inputSchema: { type: "object", properties: {} },
      action: true,
      annotations: { consequentialHint: true },
      execute: async () => {
        const err = requireTurn();
        if (err) return fail(err);
        send({ type: "end" });
        const x = await waitFor((y) => y.phase !== "running");
        return ok(summary(x));
      },
    },
    {
      name: "read_tool",
      title: "Read an analysis tool",
      description:
        "Read the current content of one of the page's analysis tools (for example Preferences, Scenario Info, Utility-based Selector, Value Histogram). Returns the tool's help text (what it does and how it works) and its components: text, tables, statistics and chart data.",
      inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
      annotations: { readOnlyHint: true },
      execute: async ({ name }) => {
        const s = st();
        const t = s?.tools.find((x) => x.name.toLowerCase() === String(name).toLowerCase());
        if (!s || !t) return fail(`No tool named ${name}. Available: ${s?.tools.map((x) => x.name).join(", ")}`);
        if (!t.enabled && !t.permanent) {
          // switching a tool on changes the participant's page: not in a read-only deployment
          if (!actionsAllowed) return fail(`${t.name} is switched off, and this page only allows reading.`);
          send({ type: "tool_layout", op: "enable", name: t.name, enabled: true });
          await sleep(1200);
        }
        const view = S().toolViews[t.id];
        return ok({ name: t.name, description: t.description, help: t.help, components: compact(view ?? []) });
      },
    },
    {
      name: "use_tool",
      title: "Use an analysis tool",
      description:
        "Interact with an analysis tool: set one of its inputs (input + value) and/or trigger one of its actions (action + payload), as listed by read_tool (inputs have a 'name', buttons an 'action', selectable tables an 'on_select').",
      inputSchema: {
        type: "object",
        properties: { name: { type: "string" }, input: { type: "string" }, value: {}, action: { type: "string" }, payload: { type: "object" } },
        required: ["name"],
      },
      action: true,
      execute: async ({ name, input, value, action, payload }) => {
        const t = st()?.tools.find((x) => x.name.toLowerCase() === String(name).toLowerCase());
        if (!t) return fail(`No tool named ${name}.`);
        if (input) send({ type: "tool_input", id: t.id, name: input, value });
        if (action) {
          flushDraftText();
          send({ type: "tool_action", id: t.id, action, payload: payload ?? {} });
        }
        await sleep(900);
        return ok({ name: t.name, components: compact(S().toolViews[t.id] ?? []), my_draft: st()?.draft });
      },
    },
    {
      name: "ask_assistant",
      title: "Ask the negotiation assistant",
      description: "Send a message to the page's built-in negotiation assistant and return its reply.",
      inputSchema: { type: "object", properties: { message: { type: "string" } }, required: ["message"] },
      action: true, // posts in the participant's chat and spends the Assistant's model calls
      execute: async ({ message }) => {
        const s = st();
        if (!s?.support) return fail("This session has no assistant.");
        const n = s.chat.length;
        send({ type: "chat", text: String(message) });
        const x = await waitFor((y) => y.chat.length > n + 1 && !y.support?.busy, 180000).catch(() => st()!);
        return ok({ replies: x.chat.slice(n).filter((m) => m.user !== "You").map((m) => m.text) });
      },
    },
    {
      name: "answer_questionnaire",
      title: "Answer the questionnaire",
      description: "Submit the post-negotiation questionnaire (question id → answer). get_negotiation_state lists the questions.",
      inputSchema: { type: "object", properties: { answers: { type: "object" } }, required: ["answers"] },
      action: true,
      execute: async ({ answers }) => {
        if (st()?.phase !== "questionnaire") return fail("No questionnaire is open.");
        send({ type: "questionnaire", answers });
        const x = await waitFor((y) => y.phase !== "questionnaire", 5000).catch(() => st()!);
        return x.phase === "questionnaire" ? fail("Some required questions are missing.") : ok(summary(x));
      },
    },
  ];
}

/** Drop presentation-only fields so the agent sees the data. */
function compact(cs: Json[]): Json[] {
  return cs.map((c) => {
    if (c.type === "plot") {
      return { type: "chart", traces: (c.figure?.data ?? []).map((t: Json) => ({ name: t.name, type: t.type, x: t.x ?? t.labels, y: t.y ?? t.values })) };
    }
    const { children, ...rest } = c;
    return children ? { ...rest, children: compact(children) } : rest;
  });
}

let controller: AbortController | null = null;
let registeredKey = "";

let actionsAllowed = false;

/** (Re-)register the tools for the current policy. Safe to call repeatedly. */
export function syncWebMCP(policy: { enabled: boolean; actions: boolean } | undefined) {
  const mc = modelContext();
  const key = policy ? `${policy.enabled}:${policy.actions}` : "off";
  if (!mc || key === registeredKey) return;
  registeredKey = key;
  actionsAllowed = !!policy?.actions;
  controller?.abort();
  controller = null;
  if (!policy?.enabled) return;
  controller = new AbortController();
  const signal = controller.signal;
  for (const t of toolDefs()) {
    if (t.action && !policy.actions) continue;
    const def = {
      name: `hani2_${t.name}`,
      title: t.title,
      description: t.description,
      inputSchema: t.inputSchema,
      annotations: { readOnlyHint: !t.action, ...(t.annotations || {}) },
      execute: async (input: Json) => {
        S().send({ type: "event", name: "webmcp", component: t.name, value: input ?? {} });
        try {
          return await t.execute(input ?? {});
        } catch (e: any) {
          return fail(String(e?.message ?? e));
        }
      },
    };
    try {
      const r = mc.registerTool(def, { signal });
      // older drafts returned {unregister()} instead of honouring the signal
      if (r && typeof r.unregister === "function") signal.addEventListener("abort", () => r.unregister());
      if (r && typeof r.catch === "function") r.catch((e: unknown) => console.warn("hani2: WebMCP registration failed", e));
    } catch (e) {
      console.warn("hani2: WebMCP registration failed", e);
    }
  }
}

export function stopWebMCP() {
  controller?.abort();
  controller = null;
  registeredKey = "";
}
