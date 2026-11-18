import { Activity, Bot, ChartColumn, Clapperboard, FileText, FolderKanban, Handshake, Map as MapIcon, Plane, Settings, Sparkles, Swords, Trophy, UsersRound, Wrench, BotMessageSquare } from "lucide-react";
import type { PageDef } from "../types";
import { entriesOf } from "../schema";
import { Analytics, Overview, Results } from "./Activity";
import { Users } from "./Users";
import { ASSISTANT_GROUPS, AUTOPILOT, AssistantSettings, Autopilot, GENERAL, General, LLM, LLM_GROUPS, NEGOTIATION, Negotiation, TOOLS_BASE, Tools, abilityEntries, toolEntries } from "./SettingsPages";
import { Texts, TEXT_KINDS } from "./Texts";
import { PROJECT_ENTRIES, Projects } from "./Projects";
import { Explorer } from "../explorer/Explorer";
import { scenariosAdapter } from "../explorer/scenarios";
import { agentsAdapter } from "../explorer/agents";
import { toolsAdapter } from "../explorer/tools";

const opponents = agentsAdapter("opponent");
const assistants = agentsAdapter("assistant");
const explorerEntries = (k: string, noun: string, group: string) => [
  { id: `${k}-groups`, label: `${group}s`, hint: `Create, edit and compose ${group.toLowerCase()}s` },
  { id: `${k}-items`, label: `All ${noun}s`, hint: `Browse every ${noun} with details`, keywords: "remove delete unlink" },
  { id: `${k}-add`, label: `Add ${noun}s`, hint: "Upload or link", keywords: "upload zip link folder file" },
];

export const PAGES: PageDef[] = [
  { id: "overview", title: "Live sessions", icon: Activity, color: "bg-good", group: "Activity", subtitle: "Everyone with a session on this server right now.", entries: [{ id: "stats", label: "Session counts", hint: "Open sessions, negotiating now, recorded sessions, events" }, { id: "sessions", label: "Sessions table" }] },
  { id: "results", title: "Results", icon: Trophy, color: "bg-warn", group: "Activity", entries: [{ id: "results-download", label: "Download results CSV" }, { id: "leaderboard", label: "Leaderboard" }, { id: "results-table", label: "Results table", hint: "Choose columns" }] },
  { id: "analytics", title: "Event analytics", icon: ChartColumn, color: "bg-opponent", group: "Activity", entries: [{ id: "events-export", label: "Export events CSV" }, { id: "events-filter", label: "Filter events", hint: "User, type, dates" }] },
  { id: "replay", title: "Replay", icon: Clapperboard, color: "bg-muted", group: "Activity", href: "/replay", Component: () => null },

  { id: "projects", title: "Projects & Studies", icon: FolderKanban, color: "bg-you", group: "Studies", subtitle: "Projects, their studies, participant links and assignments.", entries: PROJECT_ENTRIES, aliases: ["studies"] },
  { id: "texts", title: "Texts", icon: FileText, color: "bg-[#8b5cf6]", group: "Studies", subtitle: "Welcome text, consent form, scenario sets and the custom order, per layer, with a live preview.", entries: [...TEXT_KINDS.map(([k, l, h]) => ({ id: "text-editor", label: l, hint: h, keywords: k })), { id: "text-preview", label: "Text preview", hint: "Rendered with the template variables" }, { id: "text-variables", label: "Template variables", hint: "{{project_name}}, {{study_title}}, …", keywords: "variables placeholders" }, { id: "texts-in-effect", label: "Texts in effect for a study", hint: "Which layer each text comes from" }] },

  { id: "scenarios", title: "Scenarios", icon: MapIcon, color: "bg-good", group: "Library", subtitle: "Scenario types, their sets, and new ones by upload or link.", entries: [...explorerEntries("scenarios", "scenario type", "Scenario set"), { id: "scenario-default-set", label: "Default scenario set" }], aliases: ["sets"] },
  { id: "opponents", title: "Opponents", icon: Swords, color: "bg-opponent", group: "Library", subtitle: "The negotiators participants face: groups, members, and your own classes.", entries: [...explorerEntries("opponents", "opponent", "Opponent group"), { id: "opponent-pool", label: "Opponents participants face", hint: "The opponent pool", keywords: "pool opponents agents" }] },
  { id: "assistants", title: "Assistants", icon: Bot, color: "bg-you", group: "Library", subtitle: "The AI helpers on the human's side: groups, your own classes, the pool and its balance.", entries: [...explorerEntries("assistants", "Assistant", "Assistant group"), { id: "assistant-pool", label: "Assistants participants get", hint: "The Assistant pool", keywords: "pool" }, { id: "study-balance", label: "Assistant balance", hint: "Per study" }] },

  { id: "tool-library", title: "Tools", icon: Wrench, color: "bg-warn", group: "Library", subtitle: "The tools of the negotiation screen: groups, the tools sessions are offered, where each goes in each view, and your own tools.", entries: [...explorerEntries("tools", "tool", "Tool group"), { id: "tool-offer", label: "Tools offered to sessions", hint: "Which tools and tool groups a layer offers (tools.yaml offer)", keywords: "offer tools.yaml" }, { id: "tool-placement", label: "Tool placement in each view", hint: "Pane, order, shown or hidden per view (full, simple, focus)", keywords: "placement pane order visible hidden view full simple focus layout" }], aliases: ["library-tools", "placement"] },

  { id: "general", title: "General", icon: Settings, color: "bg-muted", group: "Server", aliases: ["server"], entries: entriesOf(GENERAL), Component: General },
  { id: "negotiation", title: "Negotiation", icon: Handshake, color: "bg-good", group: "Server", entries: entriesOf(NEGOTIATION), Component: Negotiation },
  { id: "tools", title: "Tool settings", icon: Wrench, color: "bg-muted", group: "Server", entries: entriesOf(TOOLS_BASE), dynamicEntries: toolEntries, Component: Tools },
  { id: "llm", title: "Language model", icon: Sparkles, color: "bg-[#8b5cf6]", group: "Server", entries: entriesOf(LLM_GROUPS), Component: LLM },
  { id: "assistant", title: "Assistant settings", icon: BotMessageSquare, color: "bg-you", group: "Server", aliases: ["agent"], entries: entriesOf(ASSISTANT_GROUPS), dynamicEntries: abilityEntries, Component: AssistantSettings },
  { id: "autopilot", title: "Autopilot", icon: Plane, color: "bg-[#0ea5e9]", group: "Server", entries: entriesOf(AUTOPILOT), Component: Autopilot },
  { id: "users", title: "Users", icon: UsersRound, color: "bg-bad", group: "Accounts", entries: [{ id: "add-user", label: "Add a user" }, { id: "user-admin", label: "Make a user an administrator" }, { id: "accounts", label: "Accounts", hint: "Set password, delete, admin" }], Component: Users },
].map((p: any) => p);

// pages whose component needs the adapters (kept out of the literal so the table stays readable)
const set = (id: string, C: PageDef["Component"]) => (PAGES.find((p) => p.id === id)!.Component = C);
set("overview", Overview);
set("results", Results);
set("analytics", Analytics);
set("projects", Projects);
set("texts", Texts);
set("scenarios", () => <Explorer adapter={scenariosAdapter} />);
set("opponents", () => <Explorer adapter={opponents} />);
set("assistants", () => <Explorer adapter={assistants} />);
set("tool-library", () => <Explorer adapter={toolsAdapter} />);
