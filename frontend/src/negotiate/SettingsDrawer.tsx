import { useEffect } from "react";
import { X } from "lucide-react";
import { send, useStore } from "../store";
import { getDeviceChoice, setDeviceChoice, type DeviceChoice } from "../device";

function Toggle({ label, hint, value, onChange }: { label: string; hint?: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2">
      <div className="flex-1">
        <div className="text-sm">{label}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <input type="checkbox" role="switch" className="mt-1 h-4 w-4 accent-[rgb(var(--you))]" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

function Num({ label, value, onChange, step = 1, nullable = false, hint }: { label: string; value: any; onChange: (v: any) => void; step?: number; nullable?: boolean; hint?: string }) {
  return (
    <label className="flex items-center gap-3 py-1.5">
      <div className="flex-1">
        <div className="text-sm">{label}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <input
        type="number"
        className="field tnum w-24"
        step={step}
        value={value ?? ""}
        placeholder={nullable ? "none" : ""}
        onChange={(e) => onChange(e.target.value === "" ? (nullable ? null : 0) : Number(e.target.value))}
      />
    </label>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="border-b border-line px-4 py-3">
    <h3 className="mb-1 text-sm font-semibold">{title}</h3>
    <div className="divide-y divide-line/60">{children}</div>
  </section>
);

export function SettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const st = useStore((s) => s.state);
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
  const a = st.settings;
  const setP = (key: string, value: any) => send({ type: "pref", key, value });
  return (
    <div className="fixed inset-0 z-[55] flex justify-end bg-[rgb(10_14_22/0.35)]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="enter flex h-full w-full max-w-sm flex-col overflow-y-auto border-l border-line bg-surface shadow-pop" role="dialog" aria-label="Settings">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="font-semibold">Settings</div>
          <button className="btn-ghost px-1.5" onClick={onClose} aria-label="Close settings">
            <X size={16} />
          </button>
        </div>
        <Section title="Display">
          <Toggle label="Show the whole history" hint="Off: only the latest offer stays visible" value={p.show_history} onChange={(v) => setP("show_history", v)} />
          <Toggle label="Show my offers in the history" value={p.show_human_offers} onChange={(v) => setP("show_human_offers", v)} />
          <Toggle label="Newest offer on top" value={p.last_offer_on_top} onChange={(v) => setP("last_offer_on_top", v)} />
          <Toggle label="Keep the offer editor open" value={p.offer_panel_always_visible} onChange={(v) => setP("offer_panel_always_visible", v)} />
          <label className="flex items-center gap-3 py-2">
            <div className="flex-1 text-sm">Offers shown as</div>
            <select className="field w-32" value={p.offer_display} onChange={(e) => setP("offer_display", e.target.value)}>
              <option value="text">Sentences</option>
              <option value="table">Issue chips</option>
            </select>
          </label>
          <label className="flex items-center gap-3 py-2">
            <div className="flex-1">
              <div className="text-sm">Layout for</div>
              <div className="text-xs text-muted">Automatic picks phone, tablet or desktop from your screen</div>
            </div>
            <select className="field w-32" defaultValue={getDeviceChoice()} onChange={(e) => setDeviceChoice(e.target.value as DeviceChoice)}>
              <option value="auto">Automatic</option>
              <option value="desktop">Desktop</option>
              <option value="tablet">Tablet</option>
              <option value="phone">Phone</option>
            </select>
          </label>
          <label className="flex items-center gap-3 py-2">
            <div className="flex-1 text-sm">Text size</div>
            <input type="range" min={0.85} max={1.3} step={0.05} value={p.font_scale ?? 1} onChange={(e) => setP("font_scale", Number(e.target.value))} className="w-32 accent-[rgb(var(--you))]" />
          </label>
        </Section>
        {st.is_admin && (
          <>
            <Section title="Timing (next negotiation)">
              <Num label="Rounds" value={a.n_steps} onChange={(v) => setP("n_steps", v)} nullable />
              <Num label="Time limit (s)" value={a.time_limit} onChange={(v) => setP("time_limit", v)} nullable />
              <Num label="Time per step (s)" value={a.step_time_limit} onChange={(v) => setP("step_time_limit", v)} nullable />
              <Num label="Negotiator time (s)" value={a.negotiator_time_limit} onChange={(v) => setP("negotiator_time_limit", v)} nullable />
              <Num label="End probability per step" value={a.pend} step={0.01} onChange={(v) => setP("pend", v)} />
              <Num label="End probability per second" value={a.pend_per_second} step={0.01} onChange={(v) => setP("pend_per_second", v)} />
            </Section>
            <Section title="Negotiation rules">
              <Toggle label="An empty offer ends the negotiation" value={a.end_on_no_response} onChange={(v) => setP("end_on_no_response", v)} />
              <Toggle label="Allow messages without an offer" value={a.allow_text_only_offers} onChange={(v) => setP("allow_text_only_offers", v)} />
              <Toggle label="Show messages from the AI partner" value={a.allow_text_agent} onChange={(v) => setP("allow_text_agent", v)} />
              <Toggle label="Let the participant write messages" value={a.allow_text_human} onChange={(v) => setP("allow_text_human", v)} />
              <Toggle label="Text-only mode" hint="The participant sends messages only" value={a.text_only_mode} onChange={(v) => setP("text_only_mode", v)} />
              <Toggle label="Write a message when none is given" hint="Uses the LLM" value={a.auto_generate} onChange={(v) => setP("auto_generate", v)} />
              <Toggle label="Start the editor from my last offer" value={a.init_with_last} onChange={(v) => setP("init_with_last", v)} />
              <Toggle label="Otherwise start from my best outcome" value={a.init_with_best} onChange={(v) => setP("init_with_best", v)} />
            </Section>
            <Section title="Scenarios and opponents">
              <Toggle label="Use saved scenario pools" hint="Off: generate a fresh scenario each time" value={a.load_existing} onChange={(v) => setP("load_existing", v)} />
              <Toggle label="Follow the scenario order" value={a.predefined_order} onChange={(v) => setP("predefined_order", v)} />
              <Toggle label="Participants may choose the scenario" value={a.allow_scenario_selection} onChange={(v) => setP("allow_scenario_selection", v)} />
              <Toggle label="Show the opponent agent's type" value={a.show_opponent_type} onChange={(v) => setP("show_opponent_type", v)} />
              <label className="block py-2">
                <div className="mb-1 text-sm">Opponent agents</div>
                <input
                  className="field"
                  defaultValue={(a.opponent_types || []).join(", ")}
                  placeholder=":template, BoulwareTBNegotiator, …"
                  onBlur={(e) => setP("opponent_types", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))}
                />
              </label>
            </Section>
            <Section title="Tools">
              <Toggle label="Tools can be switched on and off" value={a.allow_tool_switch} onChange={(v) => setP("allow_tool_switch", v)} />
              <Toggle label="Tools can be moved between panes" value={a.allow_moving_tools} onChange={(v) => setP("allow_moving_tools", v)} />
            </Section>
            <div className="px-4 py-3 text-xs text-muted">These settings apply to this session. Server-wide defaults are in Administration.</div>
          </>
        )}
      </div>
    </div>
  );
}
