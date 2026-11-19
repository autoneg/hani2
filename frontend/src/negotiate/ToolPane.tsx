import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bot, CircleHelp, EyeOff, Lock, Maximize2, MoreHorizontal, PanelBottom, PanelRight, PanelTop, Pin, Plus, X } from "lucide-react";
import { send, useStore, useUiState } from "../store";
import type { ToolInfo } from "../types";
import { Anchor } from "../ui/Anchor";
import { Icon } from "../ui/Icon";
import { Markdown } from "../ui/Markdown";
import { Modal } from "../ui/Modal";
import { Renderer } from "../ui/Renderer";

type Pane = "upper" | "lower" | "side";
const PANE_ICON = { upper: PanelTop, lower: PanelBottom, side: PanelRight };
const PANE_NAME = { upper: "Top left", lower: "Bottom left", side: "Right" };

function ToolMenu({ tool, allowMove }: { tool: ToolInfo; allowMove: boolean }) {
  const [open, setOpen] = useUiState(`toolMenu.${tool.id}`, false);
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

/** The small "?" next to a pane's tabs: opens the active tool's help text.
 * The dialog is portalled to <body> so the pane's overflow cannot clip it. */
export function ToolHelp({ tool }: { tool: ToolInfo }) {
  const [open, setOpen] = useState(false);
  const text = tool.help || tool.description;
  if (!text) return null;
  const title = (
    <span className="flex items-center gap-2">
      <Icon name={tool.icon} size={16} /> {tool.name}
    </span>
  );
  return (
    <>
      <button className="btn-ghost px-1.5 py-1" onClick={() => setOpen(true)} aria-label={`About ${tool.name}`} title={`About ${tool.name}`}>
        <CircleHelp size={15} />
      </button>
      {open &&
        createPortal(
          <Modal open onClose={() => setOpen(false)} title={title}>
            {tool.description && tool.help && <p className="mb-3 text-sm text-muted">{tool.description}</p>}
            <Markdown text={text} size="sm" />
          </Modal>,
          document.body,
        )}
    </>
  );
}

export function ToolBody({ tool }: { tool: ToolInfo }) {
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
  const maximized = useStore((s) => s.maximized);
  const canMaximize = (st?.tool_maximize ?? "window") !== "off";
  if (!st) return null;
  const tools = st.tools.filter((t) => panes.includes(t.pane) && t.visible).sort((a, b) => (panes.indexOf(a.pane) - panes.indexOf(b.pane)) * 1000 + a.order - b.order);
  const hidden = st.tools.filter((t) => panes.includes(t.pane) && !t.visible);
  const key = panes[0];
  // one tab strip for several panes (simple view, tablets, phones) keeps its own "all" tab
  const tabKey = panes.length > 1 ? "all" : key;
  let active = tools.find((t) => panes.some((p) => st.active_tabs[p] === t.name)) ?? tools[0];
  if (panes.length > 1) active = tools.find((t) => t.name === st.active_tabs[tabKey]) ?? active;
  const allowMove = st.settings.allow_moving_tools !== false && panes.length === 1;
  const allowSwitch = st.settings.allow_tool_switch !== false;
  if (!tools.length && !hidden.length) return null;
  const select = (t: ToolInfo) => {
    const pane = panes.length > 1 ? tabKey : t.pane;
    useStore.setState((s) => (s.state ? { state: { ...s.state, active_tabs: { ...s.state.active_tabs, [pane]: t.name } } } : {}));
    send({ type: "active_tab", pane, name: t.name });
  };
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
                  {t.added_by && (
                    <span className="rounded bg-you/10 px-1 text-[10px] font-medium text-you" title={`Added by ${t.added_by}`}>
                      <Bot size={11} className="inline" aria-label={`Added by ${t.added_by}`} />
                    </span>
                  )}
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
        {active && <ToolHelp key={active.id} tool={active} />}
        {active && canMaximize && maximized !== active.id && (
          <button className="btn-ghost px-1.5 py-1" onClick={() => maximize(active!)} aria-label={`Enlarge ${active.name}`} title="Enlarge">
            <Maximize2 size={14} />
          </button>
        )}
        {active && <ToolMenu key={active.id} tool={active} allowMove={allowMove} />}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3" role="tabpanel">
        {active && maximized === active.id ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <Maximize2 size={20} className="text-muted" />
            <p className="max-w-xs text-sm text-muted">{active.name} is open in a larger view.</p>
            <button className="btn-secondary" onClick={() => putBack(active!)}>
              <Pin size={14} /> Put it back here
            </button>
          </div>
        ) : active ? (
          <ToolBody key={active.id} tool={active} />
        ) : (
          <div className="text-sm text-muted">All tools here are hidden.</div>
        )}
      </div>
    </Anchor>
  );
}

function maximize(t: ToolInfo) {
  useStore.getState().setMaximized(t.id);
  send({ type: "active_tab", pane: "max", name: t.name });
  send({ type: "event", name: "tool_maximized", component: t.name });
}

function putBack(t: ToolInfo) {
  useStore.getState().setMaximized(null);
  send({ type: "active_tab", pane: "max", name: null });
  send({ type: "event", name: "tool_restored", component: t.name });
}

/** The enlarged tool: a large window or the whole screen (admin setting
 *  `tools.maximize`). "Put back" returns it to the pane it came from. */
export function MaximizedTool() {
  const id = useStore((s) => s.maximized);
  const tool = useStore((s) => s.state?.tools.find((t) => t.id === id && t.visible));
  const mode = useStore((s) => s.state?.tool_maximize ?? "window");
  useEffect(() => {
    if (id && (!tool || mode === "off")) useStore.getState().setMaximized(null);
  }, [id, tool, mode]);
  useEffect(() => {
    if (!tool) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && putBack(tool);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [tool]);
  if (!tool || mode === "off") return null;
  const full = mode === "fullscreen";
  return (
    <div
      className={`fixed inset-0 z-[58] flex ${full ? "" : "items-center justify-center bg-[rgb(10_14_22/0.5)] p-3 sm:p-6"}`}
      onMouseDown={(e) => !full && e.target === e.currentTarget && putBack(tool)}
    >
      <div
        role="dialog"
        aria-modal
        aria-label={tool.name}
        className={`enter flex min-h-0 flex-col bg-surface ${full ? "h-full w-full" : "h-[88vh] w-full max-w-6xl rounded-xl border border-line shadow-pop"}`}
      >
        <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <Icon name={tool.icon} size={16} />
          <div className="min-w-0 flex-1 truncate font-semibold">{tool.name}</div>
          <ToolHelp tool={tool} />
          <button className="btn-secondary" onClick={() => putBack(tool)} title="Return the tool to its pane (Esc)">
            <Pin size={14} /> Put back
          </button>
          <button className="btn-ghost px-1.5" onClick={() => putBack(tool)} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4">
          <ToolBody key={tool.id} tool={tool} />
        </div>
      </div>
    </div>
  );
}
