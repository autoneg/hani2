import { api } from "../../api";
import { useEffect, useState } from "react";
import { SettingsPage } from "../SettingsPage";
import { FieldGroup, Note } from "../schema";
import { Checks } from "../controls/Checks";
import { Toggle } from "../controls/Toggle";
import { Disclosure } from "../Disclosure";
import { Select } from "../controls/Select";
import { Tags } from "../controls/Tags";
import { useLayer } from "../layer";
import type { SearchEntry } from "../types";
import { Stepper } from "../controls/Stepper";
import { TextField } from "../controls/TextField";
import { InformationRows } from "./Projects";
import { Plus } from "lucide-react";

/** A switch whose default when the file does not set it is ``def``: it shows ``value ?? def`` and saves
 *  an explicit true or false (a missing key and ``null`` read differently in the backend). */
const triField = (id: string, path: string, label: string, def: boolean, hint?: string, extra: Partial<any> = {}) => ({
  id, path, label, hint, type: "custom" as const, ...extra,
  render: (s: any) => <Toggle label={label} value={s.get(path) ?? def} onChange={(x) => s.set(path, x)} />,
});

const PROVIDERS = ["ollama", "openai", "anthropic", "gemini", "azure", "groq", "mistral", "openrouter"];

/* ---------------- General (env.json, server-wide) ---------------- */
export const GENERAL: FieldGroup[] = [
  {
    title: "Identity",
    fields: [
      { id: "title", path: "title", label: "Title", hint: "Shown in the header and the browser tab", type: "text" },
      { id: "subtitle", path: "subtitle", label: "Subtitle", type: "text" },
      { id: "docs-url", path: "docs_url", label: "Help link", hint: "Where the app's help links go (empty: the HANI2 documentation)", type: "text", placeholder: "https://…" },
      { id: "public-url", path: "public_url", label: "Public address", hint: "Where participants reach this server; used in study links (HANI2_PUBLIC_URL wins)", type: "text", placeholder: "https://negotiate.example.org" },
    ],
  },
  {
    title: "Sign-in",
    fields: [
      { id: "auth-mode", path: "auth.mode", label: "Sign-in", hint: "Password, OAuth, both, or no sign-in at all", type: "select", options: [{ value: "password", label: "Username and password" }, { value: "oauth", label: "OAuth only" }, { value: "dual", label: "Password and OAuth" }, { value: "none", label: "No sign-in" }, { value: "auto", label: "Automatic (password and OAuth when a provider is set up)" }] },
      { id: "allow-registration", path: "auth.allow_registration", label: "People can create accounts", type: "toggle" },
      { id: "enforce-consent", path: "auth.enforce_consent", label: "Require consent", hint: "Participants accept the consent form before negotiating", type: "toggle", keywords: "consent.md" },
      { id: "playground", path: "playground.enabled", label: "Playground", hint: "Open /play without an account", type: "toggle" },
      { id: "admin-emails", path: "admin.emails", label: "Admin emails", hint: "OAuth users with these emails are administrators", type: "tags", placeholder: "a@uni.edu" },
      { id: "default-password-login", path: "auth.default_password_login", label: "Admins with a default password", hint: "Automatic: refused only when the server listens beyond this computer. Refuse it behind a reverse proxy on 127.0.0.1.", type: "select", options: [{ value: "auto", label: "Automatic" }, { value: "refuse", label: "Always refuse them" }, { value: "allow", label: "Always allow them" }], keywords: "admin default password security login" },
    ],
  },
  {
    title: "OAuth",
    footer: "A provider is used when it is switched on and has both a client id and a secret.",
    fields: [
      { id: "oauth-redirect", path: "oauth.redirect_uri", label: "OAuth redirect base", hint: "Public URL of this server", type: "text", placeholder: "https://negotiate.example.org" },
      { id: "github-enabled", path: "oauth.providers.github.enabled", label: "Sign in with GitHub", type: "toggle", keywords: "oauth github enabled" },
      { id: "github-key", path: "oauth.providers.github.key", label: "GitHub client id", type: "text" },
      { id: "github-secret", path: "oauth.providers.github.secret", label: "GitHub client secret", type: "password" },
      { id: "google-enabled", path: "oauth.providers.google.enabled", label: "Sign in with Google", type: "toggle", keywords: "oauth google enabled" },
      { id: "google-key", path: "oauth.providers.google.key", label: "Google client id", type: "text" },
      { id: "google-secret", path: "oauth.providers.google.secret", label: "Google client secret", type: "password" },
    ],
  },
];
GENERAL.push({
  title: "Single sign-on (hand-off)",
  footer: "Another site (a competition page, for example) signs a short-lived token with the shared secret and sends people here signed in. A provider is used only with a secret of at least 16 characters; HANI2_SSO_<NAME>_SECRET wins over the one here.",
  fields: [{ id: "sso-providers", path: "auth.sso", label: "Providers", type: "custom", wide: true, keywords: "sso hand-off single sign-on token jwt scmlweb anac", render: (s: any) => <SsoProviders value={s.get("auth.sso")} onChange={(v) => s.set("auth.sso", v)} /> }],
});

/** ``auth.sso``: one row per hand-off provider. */
function SsoProviders({ value, onChange }: { value: any; onChange: (v: any) => void }) {
  const v: Record<string, any> = value && typeof value === "object" ? value : {};
  const [name, setName] = useState("");
  const put = (n: string, k: string, x: any) => onChange({ ...v, [n]: { ...(v[n] ?? {}), [k]: x } });
  const field = (n: string, k: string, label: string, ph = "", type = "text") => (
    <label className="flex flex-col gap-0.5 text-xs text-muted">
      {label}
      <TextField label={`${n} ${label}`} type={type} value={v[n]?.[k] ?? ""} placeholder={ph} onChange={(x) => put(n, k, x)} />
    </label>
  );
  return (
    <div className="flex w-full flex-col gap-2" data-sso-providers>
      {Object.keys(v).map((n) => (
        <div key={n} className="rounded-lg border border-line p-2">
          <div className="mb-1.5 flex items-center gap-3 text-sm">
            <code>{n}</code>
            <label className="flex items-center gap-1.5 text-xs text-muted">On <Toggle label={`${n} on`} value={v[n]?.enabled !== false} onChange={(x) => put(n, "enabled", x)} /></label>
            <label className="flex items-center gap-1.5 text-xs text-muted">Trust its admin claim <Toggle label={`${n} trusts admin claim`} value={v[n]?.trust_admin_claim === true} onChange={(x) => put(n, "trust_admin_claim", x)} /></label>
            <span className="ml-auto text-xs text-muted">Remove it in the file below</span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {field(n, "secret", "Shared secret", "at least 16 characters", "password")}
            {field(n, "label", "Button label", n)}
            {field(n, "login_url", "Login page of the other site", "https://…")}
            {field(n, "issuer", "Issuer (iss)", n)}
            {field(n, "prefix", "User-name prefix", "anac_")}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <TextField label="New provider name" value={name} onChange={setName} placeholder="scmlweb" className="w-40" />
        <button type="button" className="btn-secondary text-xs" disabled={!/^[A-Za-z0-9_-]+$/.test(name) || name in v} onClick={() => (onChange({ ...v, [name]: { enabled: true } }), setName(""))}>
          <Plus size={13} /> Add a provider
        </button>
      </div>
    </div>
  );
}

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
      { id: "simple-scenarios", path: "negotiation.simple_scenarios", label: "Simple scenarios", hint: "Round numbers, linear and symmetric preferences; a project or study setting wins", type: "toggle" },
      { id: "normalized-scenarios", path: "negotiation.normalized_scenarios", label: "Normalized scenarios", hint: "Generated scenarios are normalized as negmas does it: every deal worth 0 to 1, weights adding up to 1, every value function from 0 to 1 (on by default). Off, they are kept as their generators draw them (any values; only Grocery draws such ones). Simple scenarios stay normalized, so switch them off too. A project or study setting wins", type: "toggle", keywords: "normalized normalised raw points scale generate scenarios" },
      { id: "scenario-set-session", path: "negotiation.scenario_set", label: "Scenario set", hint: "Empty: the default set (Scenarios page)", type: "custom" },
      { id: "predefined-order", path: "negotiation.predefined_order", label: "Follow the scenario order", type: "toggle" },
      { id: "allow-scenario-selection", path: "negotiation.allow_scenario_selection", label: "Participants may choose the scenario", hint: "The old switch (any type, every layer); prefer \"What participants may choose\" below", type: "toggle" },
      { id: "role-rule", path: "negotiation.role_rule", label: "Participant's role", hint: "Which side the participant plays", type: "select", options: ROLE_RULES },
      { id: "human-roles", path: "negotiation.human_roles", label: "Preferred roles", hint: "For the preferred-roles rule", type: "tags", placeholder: "Tenant" },
      { id: "human-index", path: "negotiation.human_index", label: "Seat index", hint: "For the seat-index rule (0 first)", type: "stepper", min: 0, max: 1 },
      { id: "show-opponent-type", path: "negotiation.show_opponent_type", label: "Show the opponent's type", type: "toggle" },
      { id: "opponent-types", path: "negotiation.opponent_types", label: "Opponent agents", hint: "Empty: the opponent pool (Opponents page)", type: "tags", placeholder: "BoulwareTBNegotiator" },
      { id: "human-opponent-wait", path: "negotiation.human_opponent_wait", label: "Wait for a human opponent (seconds)", hint: "Pool entries human / human+assistant; 0 waits forever", type: "stepper", min: 0, step: 30 },
      { id: "human-opponent-fallback", path: "negotiation.human_opponent_fallback", label: "AI opponent when nobody joins", type: "toggle" },
      { id: "human-opponent-absent", path: "negotiation.human_opponent_absent", label: "A human opponent has left after (seconds)", hint: "Without an open page", type: "stepper", min: 5, step: 15 },
    ],
  },
];
NEGOTIATION.push(
  {
    title: "Recording",
    fields: [triField("recording-enabled", "recording.enabled", "Record sessions", true, "Every negotiation's events and screens, for replay and evaluation (on by default). HANI2_RECORD=0 on the server switches it off whatever this says.", { keywords: "record recording replay events" })],
  },
  {
    title: "HAN league agents",
    footer: "Where the :han<year>-<set> entries of an opponent pool come from: the current year from the submitted zips, every other year from the han-agents package.",
    fields: [
      { id: "han-current-year", path: "han.current_year", label: "Current HAN year", hint: "The year whose agents come from submissions (empty: every year comes from han-agents). Never taken from the clock.", type: "stepper", min: 2000, max: 2100, nullable: true, help: "opponents.han", keywords: "han year submissions competition league" },
      { id: "han-import-dir", path: "han.import_dir", label: "Imported submissions folder", hint: "Where imported submissions are unpacked (empty: <HANI2_HOME>/han_submissions)", type: "text", mono: true, emptyNull: true, keywords: "han import submissions folder" },
      { id: "han-submissions", path: "han.submissions", label: "Submissions of each year", hint: "The folder of each year's submitted agents", type: "custom", wide: true, keywords: "han submissions folder year", render: (s: any) => <YearFolders value={s.get("han.submissions")} onChange={(v) => s.set("han.submissions", v)} /> },
    ],
  },
  {
    title: "Who knows what (every project)",
    footer: "negotiation.information: the defaults under every project's and study's own (Projects page). To clear a value set here, use its reset button, or the file below.",
    fields: [{ id: "env-information", path: "negotiation.information", label: "Information", type: "custom", wide: true, keywords: "information preferences briefing past negotiations market research control", render: (s: any) => <div className="-mx-4 -my-2.5 w-[calc(100%+2rem)]"><InformationRows value={s.get("negotiation.information")} onChange={(v) => s.set("negotiation.information", v ?? {})} inherit="Default" /></div> }],
  },
);

/** ``han.submissions``: ``{"<year>": {"dir": "<folder>"}}``. */
function YearFolders({ value, onChange }: { value: any; onChange: (v: any) => void }) {
  const v: Record<string, any> = value && typeof value === "object" ? value : {};
  const [year, setYear] = useState<number | null>(null);
  const dirOf = (x: any) => (typeof x === "string" ? x : x?.dir ?? x?.path ?? "");
  return (
    <div className="flex w-full flex-col gap-1.5">
      {Object.keys(v).sort().map((y) => (
        <div key={y} className="flex items-center gap-2">
          <code className="w-12 text-sm">{y}</code>
          <TextField label={`Submissions of ${y}`} value={dirOf(v[y])} onChange={(x) => onChange({ ...v, [y]: { dir: x } })} className="flex-1" placeholder="~/han/2027/submissions" />
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Stepper label="Year" value={year} nullable min={2000} max={2100} onChange={setYear} />
        <button type="button" className="btn-secondary text-xs" disabled={!year || String(year) in v} onClick={() => (onChange({ ...v, [String(year)]: { dir: "" } }), setYear(null))}>
          <Plus size={13} /> Add a year
        </button>
      </div>
    </div>
  );
}

/* What participants may choose (env.json → playground.choices in the settings folder, choices in a project or study) */
const CHOICE_KINDS = [
  { kind: "scenario", label: "Scenario", hint: "Any: the types of the session's scenario set", placeholder: "Trade" },
  { kind: "opponent", label: "Opponent", hint: "Any: the session's opponent pool", placeholder: "BoulwareTBNegotiator or :group" },
  { kind: "assistant", label: "Assistant", hint: "Any: the session's Assistant pool; \"none\" offers no Assistant", placeholder: "my_assistant:MyAssistant or none" },
];
export const CHOICES: FieldGroup = {
  title: "What participants may choose",
  footer: "Each negotiation starts with the scenario, opponent and Assistant chosen as usual; participants may then pick another from the allowed set. Prolific studies never allow it. In the settings folder this applies only to the playground (sessions outside any project or study); set it on a project or a study to allow it there.",
  fields: CHOICE_KINDS.map((k) => ({ id: `choose-${k.kind}`, path: `choices.${k.kind}`, label: k.label, hint: k.hint, type: "custom" as const, keywords: "choose pick select participant playground", wide: true })),
};
function ChoiceControl({ value, onChange, label, placeholder, suggestions }: { value: any; onChange: (v: any) => void; label: string; placeholder: string; suggestions?: string[] }) {
  const mode = value === true ? "any" : Array.isArray(value) ? "list" : "off";
  return (
    <div className="flex flex-col gap-2">
      <Select
        label={`${label}: who may choose`}
        value={mode}
        onChange={(m) => onChange(m === "any" ? true : m === "list" ? (Array.isArray(value) ? value : []) : false)}
        options={[{ value: "off", label: "Not allowed" }, { value: "any", label: "Any from the pool" }, { value: "list", label: "Only these" }]}
      />
      {mode === "list" && <Tags label={label} value={value} onChange={onChange} placeholder={placeholder} suggestions={suggestions} />}
    </div>
  );
}

export const Negotiation = ({ meta }: { meta: any }) => {
  const { layer } = useLayer();
  const sets = Object.keys(meta?.scenario_sets ?? {});
  const suggest: Record<string, string[]> = {
    scenario: meta?.scenario_types ?? [],
    opponent: [...Object.keys(meta?.opponent_groups ?? meta?.agent_groups ?? {}).map((g) => `:${g}`)],
    assistant: ["none"],
  };
  const choicePath = (kind: string) => (layer.kind === "settings" ? `playground.choices.${kind}` : `choices.${kind}`);
  const choices: FieldGroup = {
    ...CHOICES,
    title: layer.kind === "settings" ? "What participants may choose in the playground" : CHOICES.title,
    fields: CHOICES.fields.map((f, i) => {
      const k = CHOICE_KINDS[i];
      return { ...f, path: choicePath(k.kind), render: (s: any) => <ChoiceControl label={k.label} placeholder={k.placeholder} suggestions={suggest[k.kind]} value={s.get(choicePath(k.kind))} onChange={(v) => s.set(choicePath(k.kind), v)} /> };
    }),
  };
  const groups = [...NEGOTIATION.map((g) => ({
    ...g,
    fields: g.fields.map((f) =>
      f.id === "scenario-set-session"
        ? { ...f, render: (s: any) => <Select label="Scenario set" value={s.get("negotiation.scenario_set") ?? ""} onChange={(v) => s.set("negotiation.scenario_set", v || null)} options={[{ value: "", label: `Default${meta?.scenario_set ? ` (${meta.scenario_set})` : ""}` }, ...sets.map((k) => ({ value: k, label: k }))]} /> }
        : f,
    ),
  })), choices];
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
    { id: "pref-color-utility", path: "interface.prefs.color_utility_by_issue", label: "Colour the utility bars by issue", hint: "Each issue's share of the value, most important first; linear additive preferences only, and only when the participant knows their utilities and weights", type: "toggle", keywords: "color colour segments stacked issues weights utility bar gauge" },
    { id: "pref-last-on-top", path: "interface.prefs.last_offer_on_top", label: "Newest offer on top", type: "toggle" },
    { id: "pref-offer-panel", path: "interface.prefs.offer_panel_always_visible", label: "Keep the offer editor open", type: "toggle" },
    { id: "pref-offer-display", path: "interface.prefs.offer_display", label: "Offers shown as", type: "select", options: [{ value: "text", label: "Sentences" }, { value: "table", label: "Issue chips" }] },
    { id: "pref-show-scenario-picture", path: "interface.prefs.show_scenario_picture", label: "Show the scenario's picture", hint: "At the top of the Scenario Info tool", type: "toggle", keywords: "image picture scenario info" },
    { id: "pref-scenario-picture-style", path: "interface.prefs.scenario_picture_style", label: "Scenario picture style", hint: "Small: beside the story; Large: above it; Watermark: faintly behind it. Unset: the scenario's picture_style, else Small", type: "select", options: [{ value: "", label: "The scenario's (Small)" }, { value: "small", label: "Small" }, { value: "large", label: "Large" }, { value: "watermark", label: "Watermark" }], keywords: "image picture watermark scenario info" },
    { id: "pref-font-scale", path: "interface.prefs.font_scale", label: "Text size", hint: "1 is the normal size (0.7 to 1.6)", type: "stepper", min: 0.7, max: 1.6, step: 0.05, nullable: true, placeholder: "1", keywords: "font text size scale zoom" },
    { id: "pref-open-scenario-description", path: "interface.prefs.open_scenario_description", label: "Open the full scenario description", hint: "Expanded in the Scenario Info tool when a scenario loads", type: "toggle", keywords: "long description expanded collapsed scenario info" },
  ],
};
const INTERFACE_REST: FieldGroup[] = [
  {
    title: "Layout",
    footer: "?view= in a participant's link still chooses the starting view.",
    fields: [
      { id: "start-view", path: "interface.view", label: "Sessions start in", hint: "Simple: the negotiation and one column of tools. Full: two tool columns. Focus: no tool columns (tools open in windows). Bare: no tools at all.", type: "select", options: [{ value: "simple", label: "The simple view" }, { value: "full", label: "The full view" }, { value: "focus", label: "The focus view" }, { value: "bare", label: "The bare view (no tools)" }], keywords: "view layout simple full focus bare default start" },
      { id: "view-locked", path: "interface.view_locked", label: "Keep everyone in that view", hint: "Participants and the Assistant cannot switch views (administrators still can)", type: "toggle", keywords: "lock view layout" },
      { id: "simple-tools-side", path: "interface.simple_tools_side", label: "Tools in the simple view go", type: "select", options: [{ value: "right", label: "Right of the negotiation" }, { value: "left", label: "Left of the negotiation" }], keywords: "simple view tools side left right column" },
    ],
  },
  {
    title: "Look of the Assistant and the opponent",
    footer: "Each negotiation of a participant gets the next colour and icon of their own sequence (practice included), so two negotiations in a row never look alike.",
    fields: [
      { id: "vary-assistant-look", path: "interface.vary_appearance.assistant", label: "A different Assistant look in each negotiation", hint: "A colour and an icon of its own for the Assistant in every negotiation, so each one feels like a different Assistant", type: "toggle", keywords: "vary appearance colour color icon persona character assistant different" },
      { id: "vary-opponent-look", path: "interface.vary_appearance.opponent", label: "A different opponent look in each negotiation", hint: "A colour (and, for AI opponents, an icon) of its own for the opponent in every negotiation; a human opponent keeps the person icon", type: "toggle", keywords: "vary appearance colour color icon opponent different" },
    ],
  },
  {
    title: "Tools",
    fields: [
      { id: "allow-moving-tools", path: "negotiation.allow_moving_tools", label: "Participants may move tools between panes", hint: "The pane menu of each tool tab. The Assistant's own rearranging is its \"Rearrange tools\" ability.", type: "toggle", keywords: "move drag pane" },
      { id: "allow-tool-switch", path: "negotiation.allow_tool_switch", label: "Participants may switch tools on and off", type: "toggle" },
    ],
  },
  {
    title: "Names of the sides",
    footer: "With an Assistant, the words \"human\" and \"agent\" of a scenario can read as the participant and their opponent.",
    fields: [
      { id: "names-apply", path: "names.apply", label: "Relabel the sides", type: "select", options: [{ value: "auto", label: "When an Assistant takes part (default)" }, { value: "always", label: "Always" }, { value: "never", label: "Never" }], keywords: "names labels you opponent human agent relabel" },
      { id: "names-self", path: "names.self", label: "The participant's side", type: "text", placeholder: "You", emptyNull: true, keywords: "names labels you" },
      { id: "names-opponent", path: "names.opponent", label: "The other side", type: "text", placeholder: "Opponent", emptyNull: true, keywords: "names labels opponent" },
    ],
  },
  {
    title: "Browser AI agents (WebMCP)",
    footer: "The negotiation page can offer tools to an AI agent running in the participant's browser.",
    fields: [
      triField("webmcp-enabled", "webmcp.enabled", "Offer tools to browser AI agents", true, undefined, { keywords: "webmcp browser agent ai mcp" }),
      triField("webmcp-actions", "webmcp.actions", "They may act (send, accept, end)", true, "No: read-only tools", { keywords: "webmcp actions read-only" }),
      triField("webmcp-studies", "webmcp.studies", "Also for Prolific participants", false, "Default no, so a browser agent cannot play a study for them", { keywords: "webmcp prolific studies" }),
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
      { id: "weights-chart", path: "tools.weights_chart", label: "Issue weights shown as", hint: "In the Preferences tools. A thin bar (the default) takes much less room than the donut.", type: "select", options: [{ value: "bar", label: "A horizontal bar" }, { value: "donut", label: "A donut" }], keywords: "weights donut pie circle bar stacked preferences space compact" },
      { id: "weights-chart-window", path: "tools.weights_chart_window", label: "Issue weights in an enlarged or popped-out tool", hint: "When the Preferences tool is in its own window (enlarged or a popup) rather than pinned in a pane", type: "select", options: [{ value: "same", label: "As in the pane" }, { value: "donut", label: "A donut" }, { value: "bar", label: "A horizontal bar" }], keywords: "weights donut pie circle bar window popup enlarged maximized unpinned preferences" },
      { id: "weights-chart-switch", path: "tools.weights_chart_switch", label: "Participants may switch the weights chart", hint: "A small Bar / Donut toggle on the issue weights; it starts at the chart chosen above and the choice is kept for the session", type: "toggle", help: "tools.weights_chart_switch", keywords: "weights donut pie circle bar switch toggle choose participant human preferences" },
      { id: "preferences-scale", path: "tools.preferences_scale", label: "Preferences shown as", hint: "Normalized: percentages, every deal worth 0% to 100% and the weights as shares adding up to 100% (preferences that are not normalized are normalized for display, as negmas does it). Raw: the utility function's own numbers.", type: "select", options: [{ value: "normalized", label: "Normalized percentages" }, { value: "raw", label: "Raw numbers" }], keywords: "normalized normalised percent raw numbers scale weights values preferences" },
      { id: "values-line-above", path: "tools.values_line_above", label: "Line plot above (options)", hint: "An issue with more options than this (or a continuous one) shows its values as a line instead of bars", type: "stepper", min: 2, max: 200, keywords: "line plot bars values options many continuous preferences" },
      { id: "isolate-builtin", path: "tools.isolate_builtin", label: "Catch built-in tool failures", hint: "On: a failing built-in tool shows the failure in its own pane, like external tools always do. Off: built-in errors surface as before (for debugging HANI2).", type: "toggle", keywords: "error failure crash isolate guard exception debug broken tool" },
      { id: "render-timeout", path: "tools.render_timeout", label: "Tool render time limit (seconds)", hint: "A tool that takes longer to draw shows that it is not working; 0: no limit", type: "stepper", min: 0, step: 5, keywords: "timeout slow hang stuck tool render" },
      { id: "input-timeout", path: "tools.input_timeout", label: "Tool input and button time limit (seconds)", hint: "A tool input or button that takes longer is abandoned and the tool shows that it is not working, so the page is never stuck behind it; 0: the same limit as for rendering (and none when that is 0 too)", type: "stepper", min: 0, step: 1, keywords: "timeout slow hang stuck tool input button action" },
      { id: "show-opponent-utility", path: "tools.show_opponent_utility", label: "Participants see opponent utilities", hint: "Lets everyone switch on the opponent's utility in the Utility Plot and Trace", type: "toggle" },
      { id: "tools-extra", path: "tools.extra", label: "Extra tools", hint: "Python classes, e.g. my_pkg.tools:MyTool", type: "tags", placeholder: "pkg.mod:Tool" },
      { id: "tools-paths", path: "tools.paths", label: "Extra tool folders", hint: "Folders searched for tool files, besides the settings folder's tools/", type: "tags", placeholder: "~/my_tools", keywords: "tools paths folders directories" },
    ],
  },
  {
    title: "Scenario statistics",
    footer: "negmas statistics of every scenario (opposition, Pareto frontier, bargaining solutions), computed in the background when a negotiation starts and cached next to the scenario (_stats.yaml). Shown on the Scenarios page and in the Scenario Stats tool.",
    fields: [
      { id: "scenario-stats-enabled", path: "scenario_stats.enabled", label: "Compute scenario statistics", type: "toggle", keywords: "stats statistics pareto nash kalai opposition negmas" },
      { id: "scenario-stats-pareto-max", path: "scenario_stats.pareto_max_outcomes", label: "Keep the Pareto frontier up to (outcomes)", hint: "Larger scenarios cache every other statistic but not the frontier", type: "stepper", min: 0, step: 100000, keywords: "stats pareto frontier cache" },
      { id: "scenario-stats-timeout", path: "scenario_stats.timeout", label: "Time limit (seconds)", hint: "A scenario that takes longer is skipped", type: "stepper", min: 1, step: 30, keywords: "stats timeout slow" },
    ],
  },
];
const toolFields = (meta: any): FieldGroup => ({
  title: "Tools offered",
  footer: "Off: the tool is not offered. Admins only off: every participant gets it. Appears: when the tool shows up. Starts on: the default of its on/off switch. Guests: playground users get it. First tab: it is the front tab of its pane. Where each tool goes in each view is on the Tools page.",
  fields: (meta?.tools ?? []).map((t: any) => ({
    id: `tool-${t.name}`,
    label: t.name,
    hint: `${t.description ?? ""} — ${t.pane} pane, appears at ${t.timing}`,
    type: "custom" as const,
    render: (s: any) => {
      const disabled: string[] = s.get("tools.disabled") ?? [];
      const adminOnly = s.get(`tools.overrides.${t.name}.admin_only`) ?? t.admin_only;
      return (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
          <label className="flex items-center gap-2">
            Offered <Toggle label={`${t.name} offered`} value={!disabled.includes(t.name)} onChange={(v) => s.set("tools.disabled", v ? disabled.filter((x) => x !== t.name) : [...disabled, t.name])} />
          </label>
          <label className="flex items-center gap-2">
            Admins only <Toggle label={`${t.name} admins only`} value={!!adminOnly} onChange={(v) => s.set(`tools.overrides.${t.name}.admin_only`, v)} />
          </label>
          <label className="flex items-center gap-2">
            Appears
            <Select label={`${t.name} appears`} value={s.get(`tools.overrides.${t.name}.timing`) ?? t.timing} onChange={(v) => s.set(`tools.overrides.${t.name}.timing`, v)} options={[{ value: "always", label: "With the page" }, { value: "load", label: "When a scenario loads" }, { value: "start", label: "When the negotiation starts" }, { value: "end", label: "When it ends" }, { value: "agent", label: "Only when the Assistant adds it" }]} />
          </label>
          <label className="flex items-center gap-2">
            Starts on <Toggle label={`${t.name} starts on`} value={s.get(`tools.overrides.${t.name}.enabled`) ?? t.enabled ?? true} onChange={(v) => s.set(`tools.overrides.${t.name}.enabled`, v)} />
          </label>
          <label className="flex items-center gap-2">
            Guests <Toggle label={`${t.name} for guests`} value={s.get(`tools.overrides.${t.name}.guest`) ?? t.guest ?? true} onChange={(v) => s.set(`tools.overrides.${t.name}.guest`, v)} />
          </label>
          <label className="flex items-center gap-2">
            First tab <Toggle label={`${t.name} first tab`} value={!!(s.get(`tools.overrides.${t.name}.at_front`) ?? t.at_front)} onChange={(v) => s.set(`tools.overrides.${t.name}.at_front`, v)} />
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
      { id: "assistant-toolbox", path: "toolbox", label: "Tools it may add", hint: "Tool classes (module:Class) the Assistant may add to the page, besides the registered tools", type: "tags", placeholder: "pkg.mod:Tool", keywords: "toolbox tools assistant add" },
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
      { id: "assistant-place", path: "presentation.place", label: "The open Assistant goes", hint: "Beside the page (a dock on wide screens, sliding over the right edge otherwise), or over the tool area in the open tool's place (closing it brings the tool back). Where no tool area is shown it opens beside the page. The Assistant may change this for its session (Choose how it appears).", type: "select", options: [{ value: "beside", label: "Beside the page" }, { value: "tools", label: "Over the tool area" }], keywords: "dock panel tool area over replace place" },
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
