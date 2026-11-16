import { useEffect, useState } from "react";
import { Bot, ChevronDown, ChevronUp, Handshake, LayoutGrid, Loader2, WifiOff } from "lucide-react";
import { api, ApiError } from "../api";
import { navigate, queryParams } from "../router";
import { useStore } from "../store";
import { ActionDock, ConfirmDialog } from "./ActionDock";
import { Assistant, FloatingPanels, StatusBoard, useAutoOpenAssistant } from "./Assistant";
import { Header } from "./Header";
import { SettingsDrawer } from "./SettingsDrawer";
import { Thread } from "./Thread";
import { ToolPane } from "./ToolPane";
import { stopWebMCP, syncWebMCP } from "../webmcp";
import { useDevice } from "../device";

function useMedia(q: string) {
  const [d, setD] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = () => setD(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [q]);
  return d;
}


/** History on top; below it the action dock, with the offer generators (the
 *  side pane) next to it when `withSide` is set (the full view). */
function Center({ withSide = false, dockMax }: { withSide?: boolean; dockMax?: string }) {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-paper">
      <FloatingPanels />
      <Thread />
      {withSide ? (
        <div className="flex max-h-[64vh] min-h-[340px] shrink-0 border-t border-line">
          <ActionDock embedded />
          <div className="flex min-h-0 w-[340px] shrink-0 flex-col border-l border-line bg-surface xl:w-[400px]">
            <ToolPane panes={["side"]} className="min-h-0 flex-1" label="Offer generators" />
          </div>
        </div>
      ) : (
        <ActionDock maxHeight={dockMax} />
      )}
    </div>
  );
}

function Desktop() {
  const st = useStore((s) => s.state)!;
  const assistantOpen = useStore((s) => s.assistantOpen);
  const wide = useMedia("(min-width: 1600px)");
  const view = st.layout.view;
  const collapsed = st.layout.collapsed ?? [];
  const share = Math.max(0.2, Math.min(0.6, st.layout.sizes?.tools ?? 0.36));
  const has = (p: string) => st.tools.some((t) => t.pane === p);
  const toolsCol = view === "full" && !collapsed.includes("tools") && (has("upper") || has("lower"));
  const sideCol = view === "full" && !collapsed.includes("side") && has("side");
  const simpleCol = view === "simple" && !collapsed.includes("tools");
  return (
    <div className="flex min-h-0 flex-1">
      {toolsCol && (
        <div className="flex min-h-0 flex-col border-r border-line bg-surface" style={{ width: `${share * 100}%`, minWidth: 320 }}>
          {has("upper") && <ToolPane panes={["upper"]} className="flex-1" label="Upper tools" />}
          {has("upper") && has("lower") && <div className="h-px shrink-0 bg-line" />}
          {has("lower") && <ToolPane panes={["lower"]} className="flex-1" label="Lower tools" />}
        </div>
      )}
      <Center withSide={sideCol} />
      {simpleCol && (
        <div className="flex min-h-0 flex-col border-l border-line bg-surface" style={{ width: `${share * 100}%`, minWidth: 320 }}>
          <ToolPane panes={["upper", "lower", "side"]} className="flex-1" label="Tools" />
        </div>
      )}
      {assistantOpen &&
        (wide ? (
          <Assistant />
        ) : (
          <div className="absolute bottom-0 right-0 top-14 z-40 flex shadow-pop">
            <Assistant />
          </div>
        ))}
    </div>
  );
}

/** The assistant as a slide-over panel (tablets, narrow desktops). */
function AssistantOverlay() {
  const open = useStore((s) => s.assistantOpen);
  if (!open) return null;
  return (
    <div className="absolute bottom-0 right-0 top-14 z-40 flex w-full max-w-[420px] shadow-pop">
      <Assistant />
    </div>
  );
}

/** Tablets. Landscape: the negotiation plus one tools column. Portrait: the
 *  negotiation with a tool tray along the bottom that expands on demand. */
function Tablet({ landscape }: { landscape: boolean }) {
  const st = useStore((s) => s.state)!;
  const [trayOpen, setTrayOpen] = useState(false);
  const focus = st.layout.view === "focus";
  const hasTools = st.tools.some((t) => t.visible);
  if (landscape) {
    return (
      <div className="flex min-h-0 flex-1">
        <Center />
        {!focus && hasTools && (
          <div className="flex min-h-0 w-[42%] min-w-[340px] max-w-[520px] flex-col border-l border-line bg-surface">
            <ToolPane panes={["side", "upper", "lower"]} className="min-h-0 flex-1" label="Tools" />
          </div>
        )}
        <AssistantOverlay />
      </div>
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Center dockMax={trayOpen ? "max-h-[30vh]" : "max-h-[58vh]"} />
      {!focus && hasTools && (
        <div className={`flex shrink-0 flex-col border-t border-line bg-surface ${trayOpen ? "h-[42vh]" : ""}`}>
          <button className="flex items-center justify-between px-4 py-2.5 text-sm font-medium" onClick={() => setTrayOpen(!trayOpen)} aria-expanded={trayOpen}>
            <span className="flex items-center gap-2">
              <LayoutGrid size={16} /> Tools
            </span>
            {trayOpen ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
          </button>
          {trayOpen && <ToolPane panes={["side", "upper", "lower"]} className="min-h-0 flex-1" label="Tools" />}
        </div>
      )}
      <AssistantOverlay />
    </div>
  );
}

function Mobile() {
  const st = useStore((s) => s.state)!;
  const assistantOpen = useStore((s) => s.assistantOpen);
  const setAssistant = useStore((s) => s.setAssistantOpen);
  const [tab, setTab] = useState<"negotiate" | "tools">("negotiate");
  const current = assistantOpen ? "assistant" : tab;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1">
        {current === "negotiate" && <Center />}
        {current === "tools" && <ToolPane panes={["upper", "lower", "side"]} className="flex-1 bg-surface" label="Tools" />}
        {current === "assistant" && <Assistant />}
      </div>
      <nav className="grid shrink-0 grid-cols-3 border-t border-line bg-surface" aria-label="Sections">
        {[
          ["negotiate", Handshake, "Negotiate"],
          ["tools", LayoutGrid, "Tools"],
          ...(st.support ? [["assistant", Bot, "Assistant"]] : []),
        ].map(([k, I, l]: any) => (
          <button
            key={k}
            aria-current={current === k}
            className={`flex flex-col items-center gap-0.5 py-2 text-[11px] ${current === k ? "text-you" : "text-muted"}`}
            onClick={() => {
              if (k === "assistant") setAssistant(true);
              else {
                setAssistant(false);
                setTab(k);
              }
            }}
          >
            <I size={18} /> {l}
          </button>
        ))}
      </nav>
    </div>
  );
}

export function NegotiatePage({ mode }: { mode: "main" | "guest" }) {
  const st = useStore((s) => s.state);
  const connected = useStore((s) => s.connected);
  const connect = useStore((s) => s.connect);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState(false);
  const { device, landscape } = useDevice();
  useAutoOpenAssistant();

  useEffect(() => {
    let alive = true;
    const start = () =>
      api<{ sid: string }>("/api/session", { body: { mode, query: queryParams() } })
        .then(({ sid }) => alive && connect(sid))
        .catch((e: ApiError) => {
          if (!alive) return;
          if (e.status === 401) navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, true);
          else if (e.status === 403 && e.message === "consent_required") navigate("/consent", true);
          else setError(e.message);
        });
    start();
    const lost = () => start();
    window.addEventListener("hani-session-lost", lost);
    return () => {
      alive = false;
      window.removeEventListener("hani-session-lost", lost);
      useStore.getState().disconnect();
    };
  }, [mode, connect]);

  const webmcp = st?.webmcp;
  useEffect(() => {
    syncWebMCP(webmcp);
  }, [webmcp?.enabled, webmcp?.actions]);
  useEffect(() => () => stopWebMCP(), []);

  useEffect(() => {
    if (connected) useStore.getState().send({ type: "device", device, landscape });
  }, [connected, device, landscape]);

  useEffect(() => {
    if (connected) useStore.getState().send({ type: "event", name: "page_view", component: mode, value: { path: location.pathname, width: window.innerWidth } });
  }, [connected, mode]);

  useEffect(() => {
    if (st?.scenario?.title) document.title = `${st.scenario.title} · ${document.documentElement.dataset.brand || "HANI2"}`;
  }, [st?.scenario?.title]);

  if (error)
    return (
      <div className="flex h-screen items-center justify-center p-6 text-center">
        <div>
          <div className="mb-2 text-lg font-semibold">This page could not be opened</div>
          <p className="text-sm text-muted">{error}</p>
        </div>
      </div>
    );
  if (!st)
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-muted">
        <Loader2 size={18} className="animate-spin" /> Preparing your negotiation…
      </div>
    );
  return (
    <div className="relative flex h-[100dvh] flex-col">
      <Header onSettings={() => setSettings(true)} device={device} />
      {!connected && (
        <div className="flex items-center justify-center gap-2 bg-warn/15 px-3 py-1 text-xs text-warn" role="status">
          <WifiOff size={13} /> Reconnecting…
        </div>
      )}
      {device === "desktop" ? <Desktop /> : device === "tablet" ? <Tablet landscape={landscape} /> : <Mobile />}
      <StatusBoard />
      <ConfirmDialog />
      <SettingsDrawer open={settings} onClose={() => setSettings(false)} />
    </div>
  );
}
