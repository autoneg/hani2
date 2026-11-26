import { useEffect } from "react";
import { EyeOff, Shield, X } from "lucide-react";
import { send, useStore } from "../store";
import type { SessionState } from "../types";
import { getDeviceChoice, setDeviceChoice, type DeviceChoice } from "../device";
import { navigate } from "../router";
import { useTheme } from "./Header";

/** Whether the current user may change `key` (env.json → interface.participant_settings, per layer;
 *  admins may change everything). Missing from the state (old servers, replays): allowed. */
export const mayAdjust = (st: SessionState | null | undefined, key: string) => st?.interface?.participant_settings?.[key] !== false;

/** The participant settings shown in the drawer. */
const DRAWER_KEYS = ["show_history", "show_human_offers", "color_utility_by_issue", "last_offer_on_top", "offer_panel_always_visible", "offer_display", "show_scenario_picture", "scenario_picture_style", "open_scenario_description", "device", "font_scale", "theme"];

/** Whether the drawer has anything for this user (the header hides the settings button otherwise). */
export const drawerHasControls = (st: SessionState | null | undefined) =>
  !!st && (st.is_admin || DRAWER_KEYS.some((k) => mayAdjust(st, k)) || (!!st.support && !!(st.interface?.assistant?.choice || st.interface?.assistant?.may_hide || st.interface?.assistant?.may_show)));

function Hidden({ st, k }: { st: SessionState; k: string }) {
  if (!st.is_admin || !(st.interface?.hidden_from_participants ?? []).includes(k)) return null;
  return (
    <span className="ml-1.5 inline-flex items-center gap-0.5 rounded bg-sunken px-1 py-px align-middle text-[10px] font-medium text-muted" title="Participants of this project or study do not see this setting">
      <EyeOff size={10} /> hidden from participants
    </span>
  );
}

function Toggle({ label, hint, value, onChange, extra }: { label: string; hint?: string; value: boolean; onChange: (v: boolean) => void; extra?: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2">
      <div className="flex-1">
        <div className="text-sm">
          {label}
          {extra}
        </div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <input type="checkbox" role="switch" className="mt-1 h-4 w-4 accent-[rgb(var(--you))]" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

function Choice({ label, hint, value, onChange, options, extra }: { label: string; hint?: string; value: string; onChange: (v: string) => void; options: [string, string][]; extra?: React.ReactNode }) {
  return (
    <label className="flex items-center gap-3 py-2">
      <div className="flex-1">
        <div className="text-sm">
          {label}
          {extra}
        </div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <select className="field w-32" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="border-b border-line px-4 py-3">
    <h3 className="mb-1 text-sm font-semibold">{title}</h3>
    <div className="divide-y divide-line/60">{children}</div>
  </section>
);

/** "My settings": only what the current user may adjust. Everything else (timing, rules,
 *  scenarios, what participants may change) is in Administration, per project and study. */
export function SettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const st = useStore((s) => s.state);
  const [theme, setTheme] = useTheme();
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  useEffect(() => {
    if (st) document.documentElement.style.setProperty("--font-scale", String(st.prefs.font_scale ?? 1));
  }, [st?.prefs.font_scale]);
  if (!open || !st) return null;
  const p = st.prefs;
  const may = (k: string) => mayAdjust(st, k);
  const setP = (key: string, value: any) => send({ type: "pref", key, value });
  const h = (k: string) => <Hidden st={st} k={k} />;
  const display = DRAWER_KEYS.some(may);
  const pres = st.interface?.assistant;
  return (
    <div className="fixed inset-0 z-[55] flex justify-end bg-[rgb(10_14_22/0.35)]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="enter flex h-full w-full max-w-sm flex-col overflow-y-auto border-l border-line bg-surface shadow-pop" role="dialog" aria-label="My settings">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="font-semibold">My settings</div>
          <button className="btn-ghost px-1.5" onClick={onClose} aria-label="Close settings">
            <X size={16} />
          </button>
        </div>
        {display && (
          <Section title="Display">
            {may("show_history") && <Toggle label="Show the whole history" hint="Off: only the latest offer stays visible" value={p.show_history as boolean} onChange={(v) => setP("show_history", v)} extra={h("show_history")} />}
            {may("show_human_offers") && <Toggle label="Show my offers in the history" value={p.show_human_offers as boolean} onChange={(v) => setP("show_human_offers", v)} extra={h("show_human_offers")} />}
            {may("color_utility_by_issue") && st.utility_issues !== null && (
              <Toggle label="Colour the utility bars by issue" hint="Each issue's share of the value, most important first (additive preferences only)" value={!!p.color_utility_by_issue} onChange={(v) => setP("color_utility_by_issue", v)} extra={h("color_utility_by_issue")} />
            )}
            {may("last_offer_on_top") && <Toggle label="Newest offer on top" value={p.last_offer_on_top as boolean} onChange={(v) => setP("last_offer_on_top", v)} extra={h("last_offer_on_top")} />}
            {may("offer_panel_always_visible") && <Toggle label="Keep the offer editor open" value={p.offer_panel_always_visible as boolean} onChange={(v) => setP("offer_panel_always_visible", v)} extra={h("offer_panel_always_visible")} />}
            {may("offer_display") && (
              <Choice label="Offers shown as" value={String(p.offer_display ?? "text")} onChange={(v) => setP("offer_display", v)} options={[["text", "Sentences"], ["table", "Issue chips"]]} extra={h("offer_display")} />
            )}
            {may("show_scenario_picture") && <Toggle label="Show the scenario's picture" hint="In the Scenario Info tool" value={p.show_scenario_picture !== false} onChange={(v) => setP("show_scenario_picture", v)} extra={h("show_scenario_picture")} />}
            {may("scenario_picture_style") && (
              <Choice label="Scenario picture" hint="In the Scenario Info tool" value={String(p.scenario_picture_style ?? "")} onChange={(v) => setP("scenario_picture_style", v || null)} options={[["", "As set"], ["small", "Small"], ["large", "Large"], ["watermark", "Watermark"]]} extra={h("scenario_picture_style")} />
            )}
            {may("open_scenario_description") && <Toggle label="Open the full scenario description" hint="Expanded in the Scenario Info tool when a scenario loads" value={!!p.open_scenario_description} onChange={(v) => setP("open_scenario_description", v)} extra={h("open_scenario_description")} />}
            {may("device") && (
              <Choice
                label="Layout for"
                hint="Automatic picks phone, tablet or desktop from your screen"
                value={getDeviceChoice()}
                onChange={(v) => setDeviceChoice(v as DeviceChoice)}
                options={[["auto", "Automatic"], ["desktop", "Desktop"], ["tablet", "Tablet"], ["phone", "Phone"]]}
                extra={h("device")}
              />
            )}
            {may("theme") && <Choice label="Theme" value={theme} onChange={setTheme} options={[["system", "Automatic"], ["light", "Light"], ["dark", "Dark"]]} extra={h("theme")} />}
            {may("font_scale") && (
              <label className="flex items-center gap-3 py-2">
                <div className="flex-1 text-sm">
                  Text size
                  {h("font_scale")}
                </div>
                <input type="range" min={0.85} max={1.3} step={0.05} value={Number(p.font_scale ?? 1)} onChange={(e) => setP("font_scale", Number(e.target.value))} className="w-32 accent-[rgb(var(--you))]" />
              </label>
            )}
          </Section>
        )}
        {st.support && pres && (pres.choice || pres.may_hide || pres.may_show) && (
          <Section title="Assistant">
            {pres.choice && (
              <Choice
                label="The Assistant appears as"
                hint="A panel opened from the header, a character in the corner, or both"
                value={pres.chosen ?? pres.style}
                onChange={(v) => setP("assistant_presentation", v)}
                options={[["panel", "Panel"], ["persona", "Character"], ["both", "Both"]]}
              />
            )}
            {(pres.may_hide || pres.may_show) && (
              <Toggle
                label="Show the character"
                hint="Off: the Assistant button in the header opens the conversation"
                value={!pres.persona_hidden}
                onChange={(v) => setP("persona_hidden", !v)}
              />
            )}
          </Section>
        )}
        {st.is_admin && (
          <div className="flex flex-col gap-2 px-4 py-3 text-xs text-muted">
            <p>Timing, negotiation rules, scenarios, tools and what participants may change are set per project and study in Administration.</p>
            <button className="btn-ghost w-fit px-2 text-xs" onClick={() => navigate("/admin#interface")}>
              <Shield size={13} /> Open Administration
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
