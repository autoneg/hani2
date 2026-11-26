export type Json = any;

export interface IssueSpec {
  name: string;
  kind: "int" | "float" | "number" | "category";
  min?: number;
  max?: number;
  values?: (string | number)[];
  description?: string;
  /** shown names of some values (e.g. "agent" → "Opponent"); the value itself is what is sent */
  labels?: Record<string, string>;
  /** the control the scenario asks for in the editor */
  widget?: "buttons" | "select" | "slider" | "number";
}

export interface HistoryItem {
  id: number;
  kind: "offer" | "system";
  by?: "human" | "agent";
  name?: string;
  offer?: Record<string, Json> | null;
  offer_str?: string | null;
  /** the scenario's own view of the offer (components); absent = the default view */
  view?: Component[] | null;
  text?: string | null;
  data?: Record<string, Json> | null;
  utility?: number | null;
  below_reserved?: boolean;
  step?: number | null;
  relative_time?: number | null;
  status?: string;
  time?: number;
}

export interface ToolInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
  /** Markdown: what the tool does and how it works (the ? button). */
  help?: string;
  pane: "upper" | "lower" | "side";
  order: number;
  visible: boolean;
  enabled: boolean;
  permanent: boolean;
  /** who added the tool during the session (e.g. the Assistant's name) */
  added_by?: string | null;
}

export interface ChatMessage {
  id: string;
  user: string;
  text: string;
  kind: "text" | "question";
  time: number;
  options?: string[];
  question_id?: string;
}

export interface Highlight {
  id: string;
  target: string;
  message?: string | null;
  style: "pulse" | "glow" | "spotlight";
  duration?: number | null;
  by: string;
  time: number;
}

export interface AgentPanel {
  id: string;
  title: string;
  components: Component[];
  placement: "assistant" | "side" | "modal";
}

export interface SupportState {
  available: boolean;
  name: string;
  enabled: boolean;
  busy: boolean;
  capabilities: { key: string; label: string; description: string; granted: boolean; on: boolean }[];
  autonomy: { admin: string; user: string; effective: string };
  proactive_delivery: string;
  autopilot: boolean;
}

export interface Questionnaire {
  title?: string;
  intro?: string;
  /** pre | post | consent; absent for the per-negotiation questionnaire */
  stage?: "pre" | "post" | "consent";
  /** the consent text (Markdown) of the consent stage */
  body?: string;
  questions: {
    id: string;
    text: string;
    type: "likert5" | "likert7" | "yes_no" | "select" | "text";
    required?: boolean;
    labels?: Record<string, string>;
    options?: string[];
  }[];
}

export interface Result {
  status: string;
  ended_by: string;
  agreement: Record<string, Json> | null;
  agreement_str: string | null;
  human_utility: number | null;
  agent_utility: number | null;
  human_advantage: number | null;
  reserved_value: number;
  n_human_actions: number;
  agent_failed: boolean;
  step: number;
}

export interface SessionState {
  sid: string;
  user: string;
  display_name: string;
  mode: "main" | "guest";
  is_admin: boolean;
  admin_mode: boolean;
  /** an admin negotiating exactly as a participant would (?as_participant=1) */
  participant_view?: boolean;
  phase: "idle" | "ready" | "starting" | "running" | "ended" | "questionnaire" | "finished";
  round: { number: number; practice: boolean; label: string };
  scenario: null | {
    name: string;
    type?: string;
    title: string;
    short_description: string;
    issues: IssueSpec[];
    n_issue_columns: number;
    role: string;
    opponent_role?: string;
  };
  opponent: null | { name: string; type: string };
  negotiation: {
    running: boolean;
    thinking: boolean;
    is_my_turn: boolean;
    step: number;
    n_steps: number | null;
    relative_time: number;
    deadline: number | null;
    time_limit: number | null;
    server_time: number;
  };
  partner_offer: null | { values: Record<string, Json>; text: string; utility: number | null; message?: string | null; view?: Component[] | null };
  /** null when the human does not know it (an information split) */
  reserved_value: number | null;
  /** who knows what this round; null when the human and the Assistant know the same things */
  information?: { totals_hidden: boolean; reserved_hidden: boolean; preferences: string; past_negotiations: number; market_research: boolean } | null;
  /** ``controls``: the scenario's own counter-offer controls (components); absent = one field per issue */
  draft: { values: Record<string, Json>; text: string; utility: number | null; controls?: Component[] | null };
  result: Result | null;
  history: HistoryItem[];
  tools: ToolInfo[];
  active_tabs: Record<string, string | null>;
  reveal?: { tool: string; pane: string; seq: number } | null;
  prefs: Record<string, Json>;
  settings: Record<string, Json>;
  highlights: Highlight[];
  annotations: Record<string, { text: string; kind: string }>;
  layout: { view: "full" | "simple" | "focus" | "bare"; sizes?: Record<string, number>; collapsed?: string[]; locked?: boolean };
  /** a style sheet the Assistant added to the page (see CustomStyle) */
  custom_css?: string | null;
  /** the session's overrides of the scenario's display keys */
  display_overrides?: Record<string, Json> | null;
  agent_panels: AgentPanel[];
  board: string;
  pins?: Pin[];
  notifications?: NotificationItem[];
  interface?: InterfaceState;
  chat: ChatMessage[];
  pending_question: null | { id: string; question: string; options: string[] };
  support: SupportState | null;
  autopilot: { allowed?: boolean; available: boolean; active?: boolean; driver?: string | null; drivers?: string[] | null; can_choose?: boolean };
  notice: null | { text: string; level: string };
  /** why an assigned Assistant could not be started (the session runs without one) */
  assistant_error?: string | null;
  /** no language model of the session's model chain is available */
  model_error?: string | null;
  questionnaire: Questionnaire | null;
  finish_url: string | null;
  finish_text?: string | null;
  /** the participant did not agree to the consent form */
  finish_declined?: boolean;
  project?: string;
  study_name?: string | null;
  study: { kind: string; pid?: string; required?: number; counted?: number; practice_next?: boolean; auto_deadline?: number | null; auto_kind?: string | null; max_minutes?: number };
  can_choose_scenario: boolean;
  /** what the participant may choose for the next negotiation (null: nothing) */
  choices?: Choices | null;
  webmcp?: { enabled: boolean; actions: boolean };
  tool_maximize?: "window" | "fullscreen" | "off";
  next_opponent: string | null;
}

export interface ChoiceOption {
  value: string;
  label: string;
}

export interface Choices {
  scenario: { options: string[]; names: Record<string, string[]>; current: string | null };
  /** current: the participant's pick (null: assigned automatically) */
  opponent: { options: ChoiceOption[]; current: string | null };
  /** current: the Assistant of the next negotiation; chosen: whether the participant picked it */
  assistant: { options: ChoiceOption[]; current: string | null; chosen: boolean };
}

export interface Component {
  type: string;
  [key: string]: Json;
}

export interface Toast {
  id: number;
  message: string;
  level: "info" | "success" | "warning" | "error";
  duration?: number | null;
  action?: { label: string; kind: string } | null;
  /** system | assistant (assistant toasts come out of the persona when it is shown) */
  source?: string;
}

/** A message pinned above or below the negotiation (the screen makes room for it). */
export interface Pin {
  id: string;
  text: string;
  position: "top" | "bottom";
  level: "info" | "success" | "warning" | "error";
  source: string;
  dismissible: boolean;
}

/** A notification kept for the notification centre. */
export interface NotificationItem {
  id: number;
  message: string;
  level: "info" | "success" | "warning" | "error";
  source: string;
  time: number;
}

/** What the participant may adjust and how the Assistant appears (per layer). */
export interface InterfaceState {
  participant_settings: Record<string, boolean>;
  hidden_from_participants: string[];
  toast_ms: number;
  notification_center: boolean;
  /** style: what the page shows (a hidden character reads as "panel"); chosen: the style before hiding */
  assistant: {
    style: "panel" | "persona" | "both";
    chosen?: "panel" | "persona" | "both";
    choice: boolean;
    movable: boolean;
    persona_hidden?: boolean;
    may_hide?: boolean;
    may_show?: boolean;
  };
  move_tools: boolean;
}
