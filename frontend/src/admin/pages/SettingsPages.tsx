import { api } from "../../api";
import { useEffect, useState } from "react";
import { SettingsPage } from "../SettingsPage";
import { FieldGroup, Note } from "../schema";
import { Checks } from "../controls/Checks";
import { Toggle } from "../controls/Toggle";
import { Disclosure } from "../Disclosure";
import { Select } from "../controls/Select";
import type { SearchEntry } from "../types";

const PROVIDERS = ["ollama", "openai", "anthropic", "gemini", "azure", "groq", "mistral", "openrouter"];

/* ---------------- General (env.json, server-wide) ---------------- */
export const GENERAL: FieldGroup[] = [
  {
    title: "Identity",
    fields: [
      { id: "title", path: "title", label: "Title", hint: "Shown in the header and the browser tab", type: "text" },
      { id: "subtitle", path: "subtitle", label: "Subtitle", type: "text" },
      { id: "public-url", path: "public_url", label: "Public address", hint: "Where participants reach this server; used in study links (HANI2_PUBLIC_URL wins)", type: "text", placeholder: "https://negotiate.example.org" },
    ],
  },
  {
    title: "Sign-in",
    fields: [
      { id: "auth-mode", path: "auth.mode", label: "Sign-in", hint: "Password, OAuth, both, or no sign-in at all", type: "select", options: [{ value: "password", label: "Username and password" }, { value: "oauth", label: "OAuth only" }, { value: "dual", label: "Password and OAuth" }, { value: "none", label: "No sign-in" }] },
      { id: "allow-registration", path: "auth.allow_registration", label: "People can create accounts", type: "toggle" },
      { id: "enforce-consent", path: "auth.enforce_consent", label: "Require consent", hint: "Participants accept the consent form before negotiating", type: "toggle", keywords: "consent.md" },
      { id: "playground", path: "playground.enabled", label: "Playground", hint: "Open /play without an account", type: "toggle" },
      { id: "admin-emails", path: "admin.emails", label: "Admin emails", hint: "OAuth users with these emails are administrators", type: "tags", placeholder: "a@uni.edu" },
    ],
  },
  {
    title: "OAuth",
    footer: "A provider is used when it has both a client id and a secret.",
    fields: [
      { id: "oauth-redirect", path: "oauth.redirect_uri", label: "OAuth redirect base", hint: "Public URL of this server", type: "text", placeholder: "https://negotiate.example.org" },
      { id: "github-key", path: "oauth.providers.github.key", label: "GitHub client id", type: "text" },
      { id: "github-secret", path: "oauth.providers.github.secret", label: "GitHub client secret", type: "password" },
      { id: "google-key", path: "oauth.providers.google.key", label: "Google client id", type: "text" },
      { id: "google-secret", path: "oauth.providers.google.secret", label: "Google client secret", type: "password" },
    ],
  },
];
export const General = () => <SettingsPage kind="env" groups={GENERAL} layered={false} note={<Note>Sign-in and identity apply to the whole server, so they are saved in the shared settings folder (env.json).</Note>} />;

/* ---------------- Negotiation (env.json → negotiation, per layer) ---------------- */
const ROLE_RULES = [{ value: "auto", label: "Automatic" }, { value: "index", label: "By seat index" }, { value: "roles", label: "Preferred roles" }, { value: "alternate", label: "Alternate" }, { value: "random", label: "Random" }];
export const NEGOTIATION: FieldGroup[] = [
  {
    title: "Timing",
    footer: "Empty means no limit. Admins' own sessions have no time limit.",
    fields: [
      { id: "n-steps", path: "negotiation.n_steps", label: "Rounds", hint: "Offers each side may make", type: "stepper", min: 1, max: 10000, step: 10, nullable: true },
      { id: "time-limit", path: "negotiation.time_limit", label: "Time limit (seconds)", type: "stepper", min: 0, step: 30, nullable: true },
      { id: "step-time-limit", path: "negotiation.step_time_limit", label: "Time per step (seconds)", type: "stepper", min: 0, step: 5, nullable: true },
      { id: "negotiator-time-limit", path: "negotiation.negotiator_time_limit", label: "Negotiator time (seconds)", hint: "Total thinking time of each side", type: "stepper", min: 0, step: 10, nullable: true },
      { id: "pend", path: "negotiation.pend", label: "End probability per step", type: "stepper", min: 0, max: 1, step: 0.01 },
      { id: "pend-per-second", path: "negotiation.pend_per_second", label: "End probability per second", type: "stepper", min: 0, max: 1, step: 0.01 },
    ],
  },
  {
    title: "Negotiation rules",
    fields: [
      { id: "end-on-no-response", path: "negotiation.end_on_no_response", label: "An empty offer ends the negotiation", type: "toggle" },
      { id: "allow-text-only", path: "negotiation.allow_text_only_offers", label: "Allow messages without an offer", type: "toggle" },
      { id: "allow-text-agent", path: "negotiation.allow_text_agent", label: "Show messages from the opponent", type: "toggle" },
      { id: "allow-text-human", path: "negotiation.allow_text_human", label: "Let the participant write messages", type: "toggle" },
      { id: "text-only-mode", path: "negotiation.text_only_mode", label: "Text-only mode", hint: "The participant sends messages only", type: "toggle" },
      { id: "auto-generate", path: "negotiation.auto_generate", label: "Write a message when none is given", hint: "Uses the language model", type: "toggle" },
      { id: "auto-extract", path: "negotiation.auto_extract", label: "Read the offer out of a message", hint: "Uses the language model", type: "toggle" },
      { id: "init-with-last", path: "negotiation.init_with_last", label: "Start the editor from the participant's last offer", type: "toggle" },
      { id: "init-with-best", path: "negotiation.init_with_best", label: "Otherwise start from their best outcome", type: "toggle" },
    ],
  },
  {
    title: "Scenarios and opponents",
    fields: [
      { id: "load-existing", path: "negotiation.load_existing", label: "Use saved scenario pools", hint: "Off: generate a fresh scenario each time", type: "toggle" },
      { id: "generate-on-failure", path: "negotiation.generate_on_failure", label: "Generate a scenario when none is saved", type: "toggle" },
      { id: "scenario-set-session", path: "negotiation.scenario_set", label: "Scenario set", hint: "Empty: the default set (Scenarios page)", type: "custom" },
      { id: "predefined-order", path: "negotiation.predefined_order", label: "Follow the scenario order", type: "toggle" },
      { id: "allow-scenario-selection", path: "negotiation.allow_scenario_selection", label: "Participants may choose the scenario", type: "toggle" },
      { id: "role-rule", path: "negotiation.role_rule", label: "Participant's role", hint: "Which side the participant plays", type: "select", options: ROLE_RULES },
      { id: "human-roles", path: "negotiation.human_roles", label: "Preferred roles", hint: "For the preferred-roles rule", type: "tags", placeholder: "Tenant" },
      { id: "human-index", path: "negotiation.human_index", label: "Seat index", hint: "For the seat-index rule (0 first)", type: "stepper", min: 0, max: 1 },
      { id: "show-opponent-type", path: "negotiation.show_opponent_type", label: "Show the opponent's type", type: "toggle" },
      { id: "opponent-types", path: "negotiation.opponent_types", label: "Opponent agents", hint: "Empty: the opponent pool (Opponents page)", type: "tags", placeholder: "BoulwareTBNegotiator" },
    ],
  },
];
export const Negotiation = ({ meta }: { meta: any }) => {
  const sets = Object.keys(meta?.scenario_sets ?? {});
  const groups = NEGOTIATION.map((g) => ({
    ...g,
    fields: g.fields.map((f) =>
      f.id === "scenario-set-session"
        ? { ...f, render: (s: any) => <Select label="Scenario set" value={s.get("negotiation.scenario_set") ?? ""} onChange={(v) => s.set("negotiation.scenario_set", v || null)} options={[{ value: "", label: `Default${meta?.scenario_set ? ` (${meta.scenario_set})` : ""}` }, ...sets.map((k) => ({ value: k, label: k }))]} /> }
        : f,
    ),
  }));
  return (
    <SettingsPage
      kind="env"
      groups={groups}
      top={() => (
        <div className="mb-6 overflow-hidden rounded-xl border border-line/80 bg-surface [&>*+*]:border-t [&>*+*]:border-line/70">
          <Disclosure label="Opponents participants face" hint="Choose the opponent pool on the Opponents page" onClick={() => (location.hash = "opponents/opponent-pool")} />
          <Disclosure label="Scenario sets" hint="Choose and edit scenario sets on the Scenarios page" onClick={() => (location.hash = "scenarios/scenario-default-set")} />
          <Disclosure label="What participants may change" hint="Their own settings, moving tools, the Assistant's look" onClick={() => (location.hash = "interface")} />
        </div>
      )}
    />
  );
};

/* ---------------- Participant interface (env.json → interface, per layer) ---------------- */
const PREF_DEFAULTS: FieldGroup = {
  title: "Defaults of the participant's settings",
  footer: "What a new session starts with; a participant who may change a setting can still change it.",
  fields: [
    { id: "pref-show-history", path: "interface.prefs.show_history", label: "Show the whole history", type: "toggle" },
    { id: "pref-show-human-offers", path: "interface.prefs.show_human_offers", label: "Show the participant's offers in the history", type: "toggle" },
    { id: "pref-last-on-top", path: "interface.prefs.last_offer_on_top", label: "Newest offer on top", type: "toggle" },
    { id: "pref-offer-panel", path: "interface.prefs.offer_panel_always_visible", label: "Keep the offer editor open", type: "toggle" },
    { id: "pref-offer-display", path: "interface.prefs.offer_display", label: "Offers shown as", type: "select", options: [{ value: "text", label: "Sentences" }, { value: "table", label: "Issue chips" }] },
  ],
};
const INTERFACE_REST: FieldGroup[] = [
  {
    title: "Tools",
    fields: [
      { id: "allow-moving-tools", path: "negotiation.allow_moving_tools", label: "Participants may move tools between panes", hint: "The pane menu of each tool tab. The Assistant's own rearranging is its \"Rearrange tools\" ability.", type: "toggle", keywords: "move drag pane" },
      { id: "allow-tool-switch", path: "negotiation.allow_tool_switch", label: "Participants may switch tools on and off", type: "toggle" },
    ],
  },
  {
    title: "Notifications",
    fields: [
      { id: "toast-seconds", path: "interface.notifications.toast_seconds", label: "Notifications disappear after (seconds)", hint: "0: they stay until closed. Errors stay at least 9 seconds.", type: "stepper", min: 0, max: 120, step: 1 },
      { id: "notification-center", path: "interface.notifications.center", label: "Notification list in the header", hint: "A bell that keeps every notification of the session", type: "toggle", keywords: "bell history" },
    ],
  },
];
const participantSettings = (meta: any): FieldGroup => ({
  title: "Participants may change",
  footer: "Off: the setting is not in the participant's settings (or the control is hidden) and the server refuses the change. Administrators can always change everything.",
  fields: Object.entries(meta?.participant_settings ?? {}).map(([k, v]: any) => ({ id: `participant-${k}`, path: `interface.participant_settings.${k}`, label: v.label, hint: v.description || undefined, type: "toggle" as const, keywords: "participant user may change allow drawer settings icon" })),
});
export const INTERFACE: FieldGroup[] = [PREF_DEFAULTS, ...INTERFACE_REST];
export const interfaceEntries = (meta: any): SearchEntry[] => participantSettings(meta).fields.map((f) => ({ id: f.id, label: f.label, hint: f.hint, keywords: f.keywords }));
export const Interface = ({ meta }: { meta: any }) => (
  <SettingsPage
    kind="env"
    groups={[participantSettings(meta), ...INTERFACE]}
    top={() => (
      <div className="mb-6 overflow-hidden rounded-xl border border-line/80 bg-surface">
        <Disclosure label="How the Assistant appears" hint="Panel, character (persona), both, or the participant chooses: on the Assistant settings page" onClick={() => (location.hash = "assistant/assistant-presentation")} />
      </div>
    )}
  />
);

/* ---------------- Tools (env.json) ---------------- */
export const TOOLS_BASE: FieldGroup[] = [
  {
    title: "Tool panes",
    fields: [
      { id: "tools-maximize", path: "tools.maximize", label: "Enlarged tools open as", hint: "Each tool has an enlarge button; Put back returns it to its pane", type: "select", options: [{ value: "window", label: "A large window" }, { value: "fullscreen", label: "The full screen" }, { value: "off", label: "Not allowed" }] },
      { id: "show-opponent-utility", path: "tools.show_opponent_utility", label: "Participants see opponent utilities", hint: "Lets everyone switch on the opponent's utility in the Utility Plot and Trace", type: "toggle" },
      { id: "tools-extra", path: "tools.extra", label: "Extra tools", hint: "Python classes, e.g. my_pkg.tools:MyTool", type: "tags", placeholder: "pkg.mod:Tool" },
    ],
  },
];
const toolFields = (meta: any): FieldGroup => ({
  title: "Tools offered",
  footer: "Off: the tool is not offered. Admins only off: every participant gets it.",
  fields: (meta?.tools ?? []).map((t: any) => ({
    id: `tool-${t.name}`,
    label: t.name,
    hint: `${t.description ?? ""} — ${t.pane} pane, appears at ${t.timing}`,
    type: "custom" as const,
    render: (s: any) => {
      const disabled: string[] = s.get("tools.disabled") ?? [];
      const adminOnly = s.get(`tools.overrides.${t.name}.admin_only`) ?? t.admin_only;
      return (
        <div className="flex items-center gap-4 text-xs text-muted">
          <label className="flex items-center gap-2">
            Offered <Toggle label={`${t.name} offered`} value={!disabled.includes(t.name)} onChange={(v) => s.set("tools.disabled", v ? disabled.filter((x) => x !== t.name) : [...disabled, t.name])} />
          </label>
          <label className="flex items-center gap-2">
            Admins only <Toggle label={`${t.name} admins only`} value={!!adminOnly} onChange={(v) => s.set(`tools.overrides.${t.name}.admin_only`, v)} />
          </label>
        </div>
      );
    },
  })),
});
export const toolEntries = (meta: any): SearchEntry[] => toolFields(meta).fields.map((f) => ({ id: f.id, label: f.label, hint: f.hint, keywords: "tool" }));
export const Tools = ({ meta }: { meta: any }) => <SettingsPage kind="env" groups={[...TOOLS_BASE, toolFields(meta)]} />;

/* ---------------- Language model ---------------- */
export const LLM_GROUPS: FieldGroup[] = [
  {
    title: "Model (old single-model settings)",
    footer: "Used by the LLM offer tool, message writing, offer extraction and LLM opponents only when no model chain is set (Models page).",
    fields: [
      { id: "llm-provider", path: "provider", label: "Provider", type: "select", options: PROVIDERS },
      { id: "llm-model", path: "model", label: "Model", type: "text", placeholder: "qwen3:4b-instruct" },
      { id: "llm-ollama", path: "ollama_base_url", label: "Ollama address", type: "text" },
      { id: "llm-key", path: "api_key_env", label: "API key variable", hint: "The name of the environment variable that holds the key", type: "text", mono: true },
      { id: "llm-temperature", path: "temperature", label: "Temperature", type: "stepper", min: 0, max: 2, step: 0.1 },
      { id: "llm-max-tokens", path: "max_tokens", label: "Max tokens", type: "stepper", min: 16, step: 100 },
    ],
  },
  {
    title: "Prompts",
    footer: "Placeholders in {braces} are filled in.",
    fields: [
      { id: "llm-extraction", path: "extraction_prompt", label: "Extraction prompt", hint: "Reads an offer out of a message", type: "textarea", mono: true, rows: 8 },
      { id: "llm-generation", path: "generation_prompt", label: "Generation prompt", hint: "Writes a message for an offer", type: "textarea", mono: true, rows: 8 },
      { id: "llm-instruction", path: "instruction_prompt", label: "Instruction prompt", type: "textarea", mono: true, rows: 8 },
    ],
  },
];
function LLMStatus() {
  const [st, setSt] = useState<any>(null);
  useEffect(() => {
    api("/api/admin/llm/status").then(setSt).catch(() => {});
  }, []);
  if (!st) return null;
  return <Note tone={st.configured ? "good" : "warn"}>{st.configured ? `Ready: ${st.provider} / ${st.model}` : `Not configured: set ${st.api_key_env} or use Ollama.`}</Note>;
}
export const LLM = () => <SettingsPage kind="llm" groups={LLM_GROUPS} top={() => <LLMStatus />} />;

/* ---------------- Assistant settings ---------------- */
export const ASSISTANT_GROUPS: FieldGroup[] = [
  {
    title: "Who and what",
    footer: "Participants can narrow these permissions in their own settings, never widen them.",
    fields: [
      { id: "assistant-mode", path: "mode", label: "Who gets the Assistant", type: "select", options: [{ value: "on", label: "Everyone" }, { value: "auto", label: "Admins only" }, { value: "off", label: "Nobody" }] },
      { id: "assistant-class", path: "agent_class", label: "Assistant class", hint: "module:Class of your own Assistant; empty for the built-in one. Pools and groups are in Assistants.", type: "text", mono: true, emptyNull: true, placeholder: "my_agent:MyAgent" },
      { id: "assistant-autonomy", path: "autonomy", label: "Highest autonomy", hint: "Suggest: points at buttons. Semi: sends counter-offers, asks before accept/end. Full: acts.", type: "select", options: [{ value: "suggest", label: "Suggest" }, { value: "semi", label: "Semi" }, { value: "full", label: "Full" }] },
    ],
  },
  {
    title: "Language model",
    footer: "Old single-model settings: used only when no model chain is set for the Assistant (Models page). Temperature and max tokens also tune a chain entry that does not set them.",
    fields: [
      { id: "assistant-provider", path: "provider", label: "Provider", type: "select", options: PROVIDERS },
      { id: "assistant-model", path: "model", label: "Model", type: "text" },
      { id: "assistant-api-base", path: "api_base", label: "API base", hint: "e.g. http://localhost:11434 for a local server", type: "text", emptyNull: true },
      { id: "assistant-key", path: "api_key_env", label: "API key variable", type: "text", mono: true },
      { id: "assistant-temperature", path: "temperature", label: "Temperature", type: "stepper", min: 0, max: 2, step: 0.1 },
      { id: "assistant-max-tokens", path: "max_tokens", label: "Max tokens", type: "stepper", min: 16, step: 100 },
      { id: "assistant-tool-steps", path: "max_tool_iterations", label: "Tool steps per turn", type: "stepper", min: 1, max: 50 },
    ],
  },
  {
    title: "Speaks up unprompted when",
    fields: [
      { id: "proactive-start", path: "proactive.on_negotiation_started", label: "A negotiation starts", type: "toggle" },
      { id: "proactive-turn", path: "proactive.on_action_requested", label: "It is the participant's turn", type: "toggle" },
      { id: "proactive-end", path: "proactive.on_negotiation_ended", label: "A negotiation ends", type: "toggle" },
    ],
  },
  {
    title: "How the Assistant appears",
    footer: "Phones always show the Assistant as a tab. The character's notifications come out of it as speech bubbles.",
    fields: [
      { id: "assistant-presentation", path: "presentation.style", label: "The Assistant appears as", hint: "Panel: opened from the header. Character: a movable figure in the corner. Both. Or the participant chooses.", type: "select", options: [{ value: "panel", label: "A panel" }, { value: "persona", label: "A character (persona)" }, { value: "both", label: "Both" }, { value: "choice", label: "The participant chooses" }], keywords: "persona character avatar panel dropdown" },
      { id: "assistant-presentation-default", path: "presentation.choice_default", label: "First choice when the participant chooses", type: "select", showIf: (s) => s.get("presentation.style") === "choice", options: [{ value: "panel", label: "A panel" }, { value: "persona", label: "A character" }, { value: "both", label: "Both" }] },
      { id: "assistant-persona-movable", path: "presentation.persona_movable", label: "Participants may move the character", type: "toggle", showIf: (s) => (s.get("presentation.style") ?? "panel") !== "panel" },
    ],
  },
  { title: "System prompt", fields: [{ id: "assistant-system-prompt", path: "system_prompt", label: "System prompt", type: "textarea", rows: 12 }] },
];
const abilities = (meta: any): FieldGroup => ({
  title: "Abilities granted",
  fields: Object.entries(meta?.capabilities ?? {}).map(([k, c]: any) => ({ id: `ability-${k}`, path: `capabilities.${k}`, label: c.label, hint: c.description, type: "toggle" as const, keywords: "ability capability" })),
});
export const abilityEntries = (meta: any): SearchEntry[] => abilities(meta).fields.map((f) => ({ id: f.id, label: f.label, hint: f.hint, keywords: "ability" }));
export const AssistantSettings = ({ meta }: { meta: any }) => <SettingsPage kind="assistant" groups={[ASSISTANT_GROUPS[0], abilities(meta), ...ASSISTANT_GROUPS.slice(1)]} />;

/* ---------------- Autopilot ---------------- */
export const AUTOPILOT: FieldGroup[] = [
  {
    title: "Autopilot",
    footer: "Let an agent make every decision for the participant.",
    fields: [
      { id: "autopilot-allowed", path: "allowed", label: "Autopilot allowed", type: "toggle" },
      { id: "autopilot-driver", path: "driver", label: "Default driver", type: "custom" },
      { id: "autopilot-choose", path: "user_can_choose", label: "Participants choose the driver", hint: "Default: only in the playground", type: "custom" },
      { id: "autopilot-delay", path: "step_delay", label: "Pause between steps (s)", type: "stepper", min: 0, max: 30, step: 0.5 },
      { id: "autopilot-drivers", path: "allowed_drivers", label: "Drivers offered", hint: "None ticked offers all", type: "custom", wide: true },
    ],
  },
];
export function Autopilot({ meta }: { meta: any }) {
  const drivers: string[] = meta?.autopilot_drivers ?? [];
  const g: FieldGroup[] = [
    {
      ...AUTOPILOT[0],
      fields: AUTOPILOT[0].fields.map((f) =>
        f.id === "autopilot-driver"
          ? { ...f, type: "select" as const, options: drivers }
          : f.id === "autopilot-choose"
            ? { ...f, render: (s: any) => <ChooseDriver v={s.get("user_can_choose")} on={(x) => s.set("user_can_choose", x)} /> }
            : f.id === "autopilot-drivers"
              ? { ...f, render: (s: any) => <Checks value={s.get("allowed_drivers") ?? []} onChange={(v) => s.set("allowed_drivers", v)} options={drivers.map((d) => ({ value: d, label: d }))} /> }
              : f,
      ),
    },
  ];
  return <SettingsPage kind="autopilot" groups={g} />;
}
function ChooseDriver({ v, on }: { v: any; on: (x: any) => void }) {
  return (
    <Select label="Participants choose the driver" value={v === null || v === undefined ? "default" : v ? "yes" : "no"} onChange={(x) => on(x === "default" ? null : x === "yes")} options={[{ value: "default", label: "Playground only" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />
  );
}
