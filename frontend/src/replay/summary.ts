import type { Rec, Replay } from "./reconstruct";

export type Kind = "human" | "partner" | "assistant" | "llm" | "fn" | "click" | "questionnaire" | "system" | "input";
export const KINDS: { kind: Kind; label: string; color: string; defaultOn: boolean }[] = [
  { kind: "human", label: "Your actions", color: "#2563eb", defaultOn: true },
  { kind: "partner", label: "Partner offers", color: "#d97706", defaultOn: true },
  { kind: "assistant", label: "Assistant", color: "#7c3aed", defaultOn: true },
  { kind: "llm", label: "LLM calls", color: "#0d9488", defaultOn: true },
  { kind: "fn", label: "Functions", color: "#64748b", defaultOn: true },
  { kind: "click", label: "Clicks", color: "#94a3b8", defaultOn: true },
  { kind: "questionnaire", label: "Questionnaire", color: "#db2777", defaultOn: true },
  { kind: "system", label: "System", color: "#a3a3a3", defaultOn: false },
  { kind: "input", label: "Browser messages", color: "#cbd5e1", defaultOn: false },
];
export const COLOR: Record<string, string> = Object.fromEntries(KINDS.map((k) => [k.kind, k.color]));

export interface TimelineItem {
  t: number;
  kind: Kind;
  text: string;
  /** an action by the participant (for previous / next action) */
  action?: boolean;
  rec?: Rec;
}

const num = (v: any, d = 2) => (typeof v === "number" && isFinite(v) ? v.toFixed(d) : "?");
const short = (s: any, n = 90) => {
  const t = String(s ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
};
function values(v: any): string {
  if (!v || typeof v !== "object") return "";
  return Object.entries(v)
    .map(([k, x]) => `${k}=${x}`)
    .join(", ");
}
const who = (actor: string) => (actor === "human" ? "You" : actor === "autopilot" ? "Autopilot" : "Assistant");

function tokens(u: any) {
  return u?.total_tokens ?? (u?.prompt_tokens || 0) + (u?.completion_tokens || 0);
}

export function describeClick(target: any): string {
  const name = target?.label || target?.text || target?.anchor || target?.id || target?.sel || "";
  const what = target?.tag === "button" || target?.tag === "a" ? target.tag : target?.tag === "input" ? "field" : target?.tag === "textarea" ? "text box" : target?.tag || "element";
  return `Clicked ${name ? `'${short(name, 40)}' ` : ""}${what}`;
}

export function buildTimeline(r: Replay): TimelineItem[] {
  const out: TimelineItem[] = [];
  const add = (t: number, kind: Kind, text: string, rec?: Rec, action = false) => out.push({ t, kind, text, rec, action });
  for (const e of r.events) {
    const t = Number(e.t) || 0;
    switch (e.k) {
      case "act": {
        const a = String(e.actor || "human");
        const kind: Kind = a === "human" ? "human" : "assistant";
        if (e.type === "offer") add(t, kind, `${who(a)} offered ${values(e.values) || "an offer"}${e.utility != null ? ` (utility ${num(e.utility)})` : ""}${e.text ? `: "${short(e.text, 60)}"` : ""}`, e, a === "human");
        else if (e.type === "accept") add(t, kind, `${who(a)} accepted the offer`, e, a === "human");
        else if (e.type === "end") add(t, kind, `${who(a)} ended the negotiation`, e, a === "human");
        else if (e.type === "text") add(t, kind, `${who(a)} wrote: "${short(e.text)}"`, e, a === "human");
        break;
      }
      case "chat":
        if (e.user === "You") add(t, "human", `You to assistant: ${short(e.text)}`, e, true);
        else add(t, "assistant", `${e.user || "Assistant"}: ${short(e.text)}`, e);
        break;
      case "draft":
        add(t, e.by === "human" ? "human" : "assistant", `${e.by === "human" ? "You" : "Assistant"} edited the draft (utility ${num(e.utility)})`, e);
        break;
      case "llm":
        add(t, "llm", `LLM call (${e.role}, ${e.model ?? "?"}, ${num(e.latency, 1)} s, ${tokens(e.usage)} tok${e.error ? ", error" : ""})`, e);
        break;
      case "fn":
        add(t, "fn", `fn ${e.name}(${short(JSON.stringify(e.args ?? {}).replace(/^\{|\}$/g, ""), 60)})`, e);
        break;
      case "questionnaire":
        add(t, "questionnaire", `Questionnaire answered: ${short(values(e.answers), 120)}`, e, true);
        break;
      case "ev":
        add(t, "system", `${e.type}${e.component ? " " + e.component : ""}${e.action ? " " + e.action : ""}${e.value != null && typeof e.value !== "object" ? " " + short(e.value, 40) : ""}`, e);
        break;
      case "start":
        add(t, "system", `Negotiation started${e.opponent ? ` with ${e.opponent}` : ""}`, e);
        break;
      case "result":
        add(t, "system", `Result: ${e.summary?.status ?? "finished"}${e.summary?.human_utility != null ? ` (you ${num(e.summary.human_utility)}, partner ${num(e.summary.agent_utility)})` : ""}`, e);
        break;
      case "scenario":
        add(t, "system", `Scenario ${e.name ?? ""} loaded`, e);
        break;
      case "in":
        add(t, "input", `Browser sent ${e.msg?.type ?? "message"}${e.msg?.text ? `: "${short(e.msg.text, 50)}"` : ""}`, e);
        break;
    }
  }
  // clicks and typing from the telemetry
  for (const c of r.clicks) add(c.t, "click", describeClick(c.target), undefined, false);
  let lastKey = -9;
  for (const k of r.keys) {
    if (k.v === "char" && k.t - lastKey < 2) continue;
    lastKey = k.t;
    if (k.v === "char") add(k.t, "input", "Typed", undefined, false);
  }
  // partner offers: new offers by the other side in the history the browser received
  const seen = new Set<any>();
  for (const m of r.msgs) {
    const items: any[] | undefined = m.type === "state" ? m.data?.history : m.type === "history" ? m.data?.items : undefined;
    if (!items) continue;
    for (const it of items) {
      if (seen.has(it.id)) continue;
      seen.add(it.id);
      if (it.kind === "offer" && it.by === "agent" && !m.carry)
        add(m.t, "partner", `Partner offered ${it.offer_str || values(it.offer)}${it.text ? `: "${short(it.text, 60)}"` : ""}${it.utility != null ? ` (worth ${num(it.utility)} to you)` : ""}`);
    }
  }
  out.sort((a, b) => a.t - b.t);
  return out;
}
