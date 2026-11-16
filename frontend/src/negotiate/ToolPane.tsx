import { useEffect, useRef, useState } from "react";
import { EyeOff, Lock, MoreHorizontal, PanelBottom, PanelRight, PanelTop, Plus } from "lucide-react";
import { send, useStore } from "../store";
import type { ToolInfo } from "../types";
import { Anchor } from "../ui/Anchor";
import { Icon } from "../ui/Icon";
import { Renderer } from "../ui/Renderer";

type Pane = "upper" | "lower" | "side";
const PANE_ICON = { upper: PanelTop, lower: PanelBottom, side: PanelRight };
const PANE_NAME = { upper: "Top left", lower: "Bottom left", side: "Right" };

function ToolMenu({ tool, allowMove }: { tool: ToolInfo; allowMove: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost px-1.5 py-1" onClick={() => setOpen(!open)} aria-label={`${tool.name} options`}>
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div className="enter absolute right-0 top-full z-40 mt-1 w-48 rounded-xl border border-line bg-surface p-1 shadow-pop" onClick={() => setOpen(false)}>
          {allowMove &&
            (["upper", "lower", "side"] as Pane[])
              .filter((p) => p !== tool.pane)
              .map((p) => {
                const I = PANE_ICON[p];
                return (
                  <button key={p} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm hover:bg-sunken" onClick={() => send({ type: "tool_layout", op: "move", name: tool.name, pane: p })}>
                    <I size={15} /> Move to {PANE_NAME[p].toLowerCase()}
                  </button>
                );
              })}
          {!tool.permanent && (
            <button className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm hover:bg-sunken" onClick={() => send({ type: "tool_layout", op: "hide", name: tool.name })}>
              <EyeOff size={15} /> Hide this tool
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ToolBody({ tool }: { tool: ToolInfo }) {
  const view = useStore((s) => s.toolViews[tool.id]);
  const rv = useStore((s) => s.state?.reserved_value);
  const allowSwitch = useStore((s) => s.state?.settings.allow_tool_switch !== false);
  const disabled = !tool.enabled && !tool.permanent && allowSwitch;
  if (disabled) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <Lock size={20} className="text-muted" />
        <p className="max-w-xs text-sm text-muted">{tool.description || "This tool is switched off."}</p>
        <button className="btn-secondary" onClick={() => send({ type: "tool_layout", op: "enable", name: tool.name, enabled: true })}>
          Turn on {tool.name}
        </button>
      </div>
    );
  }
  if (!view) return <div className="h-24 animate-pulse rounded-lg bg-sunken" />;
  return (
    <Renderer
      components={view}
      ctx={{
        reserved: rv,
        onInput: (name, value) => send({ type: "tool_input", id: tool.id, name, value }),
        onAction: (action, payload) => send({ type: "tool_action", id: tool.id, action, payload }),
      }}
    />
  );
}

export function ToolPane({ panes, className = "", label }: { panes: Pane[]; className?: string; label?: string }) {
  const st = useStore((s) => s.state);
  if (!st) return null;
  const tools = st.tools.filter((t) => panes.includes(t.pane) && t.visible).sort((a, b) => (panes.indexOf(a.pane) - panes.indexOf(b.pane)) * 1000 + a.order - b.order);
  const hidden = st.tools.filter((t) => panes.includes(t.pane) && !t.visible);
  const key = panes[0];
  let active = tools.find((t) => panes.some((p) => st.active_tabs[p] === t.name)) ?? tools[0];
  if (panes.length > 1) active = tools.find((t) => t.name === st.active_tabs[key]) ?? active;
  const allowMove = st.settings.allow_moving_tools !== false && panes.length === 1;
  const allowSwitch = st.settings.allow_tool_switch !== false;
  if (!tools.length && !hidden.length) return null;
  const select = (t: ToolInfo) => send({ type: "active_tab", pane: panes.length > 1 ? key : t.pane, name: t.name });
  return (
    <Anchor id={`pane:${key}`} className={`flex min-h-0 flex-col ${className}`}>
      <div className="flex items-center gap-1 border-b border-line px-2" role="tablist" aria-label={label ?? "Tools"}>
        <div className="scroll-thin flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
          {tools.map((t) => {
            const on = active?.id === t.id;
            return (
              <Anchor id={`tool:${t.name}`} key={t.id} className="shrink-0">
                <button
                  role="tab"
                  aria-selected={on}
                  title={t.description}
                  onClick={() => select(t)}
                  className={`relative flex items-center gap-1.5 whitespace-nowrap px-2.5 py-2.5 text-[0.8rem] font-medium transition-colors ${on ? "text-ink" : "text-muted hover:text-ink"} ${!t.enabled && !t.permanent && allowSwitch ? "opacity-60" : ""}`}
                >
                  <Icon name={t.icon} size={14} />
                  {t.name}
                  {on && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-you" />}
                </button>
              </Anchor>
            );
          })}
        </div>
        {hidden.length > 0 && (
          <div className="group relative">
            <button className="btn-ghost px-1.5 py-1" aria-label="Show hidden tools" title="Show hidden tools">
              <Plus size={15} />
            </button>
            <div className="invisible absolute right-0 top-full z-40 w-52 rounded-xl border border-line bg-surface p-1 opacity-0 shadow-pop transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
              {hidden.map((t) => (
                <button key={t.id} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm hover:bg-sunken" onClick={() => send({ type: "tool_layout", op: "show", name: t.name })}>
                  <Icon name={t.icon} size={14} /> {t.name}
                </button>
              ))}
            </div>
          </div>
        )}
        {active && !active.permanent && allowSwitch && (
          <label className="flex shrink-0 cursor-pointer items-center gap-1.5 px-1 text-xs text-muted" title={active.enabled ? "Turn this tool off" : "Turn this tool on"}>
            <span className="sr-only">Enabled</span>
            <input
              type="checkbox"
              role="switch"
              className="peer sr-only"
              checked={active.enabled}
              onChange={(e) => send({ type: "tool_layout", op: "enable", name: active!.name, enabled: e.target.checked })}
            />
            <span className="relative h-4 w-7 rounded-full bg-line transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-surface after:transition-transform peer-checked:bg-you peer-checked:after:translate-x-3 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-you" />
          </label>
        )}
        {active && <ToolMenu tool={active} allowMove={allowMove} />}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3" role="tabpanel">
        {active ? <ToolBody key={active.id} tool={active} /> : <div className="text-sm text-muted">All tools here are hidden.</div>}
      </div>
    </Anchor>
  );
}
