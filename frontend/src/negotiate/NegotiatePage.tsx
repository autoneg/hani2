import { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, ChevronUp, Handshake, LayoutGrid, Loader2, WifiOff } from "lucide-react";
import { api, ApiError } from "../api";
import { currentPath, navigate, queryParams } from "../router";
import { useStore, useUiState } from "../store";
import { ActionDock, ConfirmDialog } from "./ActionDock";
import { Assistant, FloatingPanels, StatusBoard, useAutoOpenAssistant } from "./Assistant";
import { Header } from "./Header";
import { SettingsDrawer } from "./SettingsDrawer";
import { Thread } from "./Thread";
import { MaximizedTool, ToolPane } from "./ToolPane";
import { stopWebMCP, syncWebMCP } from "../webmcp";
import { useDevice, type Device } from "../device";
import * as telemetry from "../telemetry";
import { Splitter, useLayoutSize } from "../ui/Splitter";
import { PinnedMessages } from "./Notifications";
import { Persona, assistantStyle } from "./Persona";

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
 *  side pane) next to it when `withSide` is set (the full view). Dividers
 *  resize the dock against the history and the generators against the dock. */
function Center({ withSide = false, dockMax, prefix = "" }: { withSide?: boolean; dockMax?: string; prefix?: string }) {
  const centerRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  const sideRef = useRef<HTMLDivElement>(null);
  const [dock, setDock, commitDock] = useLayoutSize(`${prefix}dock`);
  const [side, setSide, commitSide] = useLayoutSize("side");
  const share = (el: HTMLElement | null, of: HTMLElement | null, h: boolean) =>
    el && of ? (h ? el.offsetHeight / Math.max(1, of.offsetHeight) : el.offsetWidth / Math.max(1, of.offsetWidth)) : 0.4;
  const assistantError = useStore((s) => s.state?.assistant_error);
  const modelError = useStore((s) => s.state?.model_error);
  return (
    <div ref={centerRef} className="flex min-h-0 min-w-0 flex-1 flex-col bg-paper">
      {assistantError && (
        <div role="alert" className="mx-3 mt-3 shrink-0 rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">
          The Assistant could not be started, so this session runs without it. {assistantError}
        </div>
      )}
      {modelError && !assistantError && (
        <div role="alert" className="mx-3 mt-3 shrink-0 rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">
          {modelError}
        </div>
      )}
      <FloatingPanels />
      <Thread />
      <Splitter
        dir="row"
        after
        container={centerRef}
        value={dock}
        fallback={() => share(dockRef.current, centerRef.current, true)}
        onChange={setDock}
        onCommit={commitDock}
        min={0.2}
        max={0.88}
        label="Resize the offer area"
      />
      <div ref={dockRef} className="flex min-h-0 shrink-0 flex-col" style={dock !== undefined ? { height: `${dock * 100}%` } : undefined}>
        {withSide ? (
          <div ref={rowRef} className={`flex min-h-0 flex-1 ${dock === undefined ? "max-h-[64vh] min-h-[340px]" : ""}`}>
            <ActionDock embedded />
            <Splitter
              dir="col"
              after
              container={rowRef}
              value={side}
              fallback={() => share(sideRef.current, rowRef.current, false)}
              onChange={setSide}
              onCommit={commitSide}
              min={0.2}
              max={0.65}
              label="Resize the offer generators"
            />
            <div
              ref={sideRef}
              className={`flex min-h-0 min-w-[240px] flex-col bg-surface ${side === undefined ? "w-[340px] shrink-0 xl:w-[400px]" : "shrink"}`}
              style={side !== undefined ? { width: `${side * 100}%` } : undefined}
            >
              <ToolPane panes={["side"]} className="min-h-0 flex-1" label="Offer generators" />
            </div>
          </div>
        ) : dock === undefined ? (
          <ActionDock maxHeight={dockMax} />
        ) : (
          <ActionDock embedded />
        )}
      </div>
    </div>
  );
}

/** A column of upper / lower tool panes with a divider between them. */
function ToolColumn() {
  const st = useStore((s) => s.state)!;
  const ref = useRef<HTMLDivElement>(null);
  const upperRef = useRef<HTMLDivElement>(null);
  const [upper, setUpper, commitUpper] = useLayoutSize("upper");
  const has = (p: string) => st.tools.some((t) => t.pane === p);
  const u = upper ?? 0.5;
  if (!(has("upper") && has("lower")))
    return <ToolPane panes={[has("upper") ? "upper" : "lower"]} className="min-h-0 flex-1" label="Tools" />;
  return (
    <div ref={ref} className="flex min-h-0 flex-1 flex-col">
      <div ref={upperRef} className="flex min-h-0 flex-col" style={{ flex: `${u} 1 0%` }}>
        <ToolPane panes={["upper"]} className="min-h-0 flex-1" label="Upper tools" />
      </div>
      <Splitter
        dir="row"
        container={ref}
        value={upper}
        fallback={() => 0.5}
        onChange={setUpper}
        onCommit={commitUpper}
        min={0.12}
        max={0.88}
        label="Resize the upper and lower tools"
      />
      <div className="flex min-h-0 flex-col" style={{ flex: `${1 - u} 1 0%` }}>
        <ToolPane panes={["lower"]} className="min-h-0 flex-1" label="Lower tools" />
      </div>
    </div>
  );
}

function Desktop() {
  const st = useStore((s) => s.state)!;
  const assistantOpen = useStore((s) => s.assistantOpen) && assistantStyle(st, "desktop") !== "persona";
  const wide = useMedia("(min-width: 1600px)");
  const rowRef = useRef<HTMLDivElement>(null);
  const [tools, setTools, commitTools] = useLayoutSize("tools");
  const [asst, setAsst, commitAsst] = useLayoutSize("assistant");
  const view = st.layout.view;
  const collapsed = st.layout.collapsed ?? [];
  const share = Math.max(0.15, Math.min(0.7, tools ?? 0.36));
  const has = (p: string) => st.tools.some((t) => t.pane === p);
  const toolsCol = view === "full" && !collapsed.includes("tools") && (has("upper") || has("lower"));
  const sideCol = view === "full" && !collapsed.includes("side") && has("side");
  const simpleCol = view === "simple" && !collapsed.includes("tools");
  const toolsSplitter = (after: boolean) => (
    <Splitter
      dir="col"
      after={after}
      container={rowRef}
      value={tools}
      fallback={() => share}
      onChange={setTools}
      onCommit={commitTools}
      min={0.15}
      max={0.7}
      label="Resize the tools"
    />
  );
  return (
    <div ref={rowRef} className="flex min-h-0 flex-1">
      {toolsCol && (
        <>
          <div className="flex min-h-0 flex-col bg-surface" style={{ width: `${share * 100}%`, minWidth: 240 }}>
            <ToolColumn />
          </div>
          {toolsSplitter(false)}
        </>
      )}
      <Center withSide={sideCol} />
      {simpleCol && (
        <>
          {toolsSplitter(true)}
          <div className="flex min-h-0 flex-col bg-surface" style={{ width: `${share * 100}%`, minWidth: 240 }}>
            <ToolPane panes={["upper", "lower", "side"]} className="flex-1" label="Tools" />
          </div>
        </>
      )}
      {assistantOpen &&
        (wide ? (
          <>
            <Splitter
              dir="col"
              after
              container={rowRef}
              value={asst}
              fallback={() => 360 / Math.max(1, rowRef.current?.offsetWidth ?? 1600)}
              onChange={setAsst}
              onCommit={commitAsst}
              min={0.15}
              max={0.45}
              label="Resize the assistant"
            />
            <div className="flex min-h-0 shrink-0" style={{ width: asst !== undefined ? `${asst * 100}%` : 360 }}>
              <Assistant fill />
            </div>
          </>
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
  const persona = useStore((s) => assistantStyle(s.state, "tablet") === "persona");
  if (!open || persona) return null;
  return (
    <div className="absolute bottom-0 right-0 top-14 z-40 flex w-full max-w-[420px] shadow-pop">
      <Assistant />
    </div>
  );
}

/** Re-runs `fn` whenever the server asks to reveal a tool (e.g. the
 *  participant's own preferences when a negotiation starts). */
function useReveal(fn: () => void) {
  const seq = useStore((s) => s.state?.reveal?.seq);
  const seen = useRef(seq);
  useEffect(() => {
    if (seq !== undefined && seq !== seen.current) {
      seen.current = seq;
      fn();
    }
  }, [seq]);
}

/** Tablets. Landscape: the negotiation plus one tools column. Portrait: the
 *  negotiation with a tool tray along the bottom that expands on demand. */
function Tablet({ landscape }: { landscape: boolean }) {
  const st = useStore((s) => s.state)!;
  const [trayOpen, setTrayOpen] = useUiState("tablet.tray", false);
  const rowRef = useRef<HTMLDivElement>(null);
  const colRef = useRef<HTMLDivElement>(null);
  const [tools, setTools, commitTools] = useLayoutSize("tablet_tools");
  const [tray, setTray, commitTray] = useLayoutSize("tray");
  useReveal(() => setTrayOpen(true));
  const focus = st.layout.view === "focus";
  const hasTools = st.tools.some((t) => t.visible);
  if (landscape) {
    const w = tools ?? 0.42;
    return (
      <div ref={rowRef} className="flex min-h-0 flex-1">
        <Center prefix="tablet_" />
        {!focus && hasTools && (
          <>
            <Splitter dir="col" after container={rowRef} value={tools} fallback={() => w} onChange={setTools} onCommit={commitTools} min={0.25} max={0.65} label="Resize the tools" />
            <div className="flex min-h-0 flex-col bg-surface" style={{ width: `${w * 100}%`, minWidth: 280 }}>
              <ToolPane panes={["side", "upper", "lower"]} className="min-h-0 flex-1" label="Tools" />
            </div>
          </>
        )}
        <AssistantOverlay />
      </div>
    );
  }
  const h = tray ?? 0.42;
  return (
    <div ref={colRef} className="flex min-h-0 flex-1 flex-col">
      <Center prefix="tablet_" dockMax={trayOpen ? "max-h-[30vh]" : "max-h-[58vh]"} />
      {!focus && hasTools && (
        <>
          {trayOpen && (
            <Splitter dir="row" after container={colRef} value={tray} fallback={() => h} onChange={setTray} onCommit={commitTray} min={0.2} max={0.8} label="Resize the tools" />
          )}
          <div className={`flex shrink-0 flex-col bg-surface ${trayOpen ? "" : "border-t border-line"}`} style={trayOpen ? { height: `${h * 100}%` } : undefined}>
            <button className="flex items-center justify-between px-4 py-2.5 text-sm font-medium" onClick={() => setTrayOpen(!trayOpen)} aria-expanded={trayOpen}>
              <span className="flex items-center gap-2">
                <LayoutGrid size={16} /> Tools
              </span>
              {trayOpen ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
            </button>
            {trayOpen && <ToolPane panes={["side", "upper", "lower"]} className="min-h-0 flex-1" label="Tools" />}
          </div>
        </>
      )}
      <AssistantOverlay />
    </div>
  );
}

function Mobile() {
  const st = useStore((s) => s.state)!;
  const assistantOpen = useStore((s) => s.assistantOpen);
  const setAssistant = useStore((s) => s.setAssistantOpen);
  const [tab, setTab] = useUiState<"negotiate" | "tools">("mobile.tab", "negotiate");
  useReveal(() => {
    setAssistant(false);
    setTab("tools");
  });
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

/** The negotiation screen itself (no networking): shared by the live page and the replay frame. */
export function NegotiateBody({ device, landscape, live = true }: { device: Device; landscape: boolean; live?: boolean }) {
  const connected = useStore((s) => s.connected);
  const [settings, setSettings] = useUiState("settingsDrawer", false);
  return (
    <div className="relative flex h-[100dvh] flex-col">
      <Header onSettings={() => setSettings(true)} device={device} />
      {live && !connected && (
        <div className="flex items-center justify-center gap-2 bg-warn/15 px-3 py-1 text-xs text-warn" role="status">
          <WifiOff size={13} /> Reconnecting…
        </div>
      )}
      <PinnedMessages position="top" live={live} />
      {device === "desktop" ? <Desktop /> : device === "tablet" ? <Tablet landscape={landscape} /> : <Mobile />}
      <PinnedMessages position="bottom" live={live} />
      <StatusBoard />
      <Persona device={device} live={live} />
      <MaximizedTool />
      <ConfirmDialog />
      <SettingsDrawer open={settings} onClose={() => setSettings(false)} />
    </div>
  );
}

export function NegotiatePage({ mode }: { mode: "main" | "guest" }) {
  const st = useStore((s) => s.state);
  const connected = useStore((s) => s.connected);
  const connect = useStore((s) => s.connect);
  const [error, setError] = useState<string | null>(null);
  const { device, landscape } = useDevice();
  useAutoOpenAssistant();

  useEffect(() => {
    telemetry.start();
    return () => telemetry.stop();
  }, []);
  useEffect(() => {
    telemetry.setDevice(device, landscape);
  }, [device, landscape]);

  useEffect(() => {
    let alive = true;
    const start = () =>
      api<{ sid: string }>("/api/session", { body: { mode, query: queryParams() } })
        .then(({ sid }) => alive && connect(sid))
        .catch((e: ApiError) => {
          if (!alive) return;
          if (e.status === 401) navigate(`/login?next=${encodeURIComponent(currentPath() + location.search)}`, true);
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
    if (connected) useStore.getState().send({ type: "event", name: "page_view", component: mode, value: { path: currentPath(), width: window.innerWidth } });
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
  return <NegotiateBody device={device} landscape={landscape} />;
}
