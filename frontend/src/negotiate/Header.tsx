import { useEffect, useRef, useState } from "react";
import { Bot, Columns3, KeyRound, LayoutPanelLeft, LogOut, Maximize2, Moon, Plane, Settings2, Shield, Sun, SunMoon, UserRound } from "lucide-react";
import { send, useStore, useUiState } from "../store";
import { isVirtual, now as clockNow } from "../clock";
import { Anchor } from "../ui/Anchor";
import { clock } from "../ui/format";
import { api } from "../api";
import { navigate } from "../router";
import { webmcpAvailable } from "../webmcp";
import { Modal } from "../ui/Modal";

let brandCache: string | null = null;
function useBrand(explicit?: string) {
  const [t, setT] = useState<string>(explicit ?? brandCache ?? "HANI2");
  useEffect(() => {
    if (explicit) return;
    if (brandCache) return setT(brandCache);
    api("/api/config")
      .then((c) => {
        brandCache = c.title || "HANI2";
        document.documentElement.dataset.brand = brandCache!;
        setT(brandCache!);
      })
      .catch(() => {});
  }, [explicit]);
  return explicit ?? t;
}

export function Brand({ title: explicit }: { title?: string }) {
  const title = useBrand(explicit);
  return (
    <div className="flex items-center gap-2">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-ink" />
        <path d="M7 20.5h8.5V11H7z" className="fill-you" />
        <path d="M16.5 21H25v-9.5h-8.5z" className="fill-opponent" />
        <path d="M7 23h18" stroke="rgb(var(--surface))" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className="text-[1.05rem] font-semibold tracking-tight">{title}</span>
    </div>
  );
}

export function useTheme() {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem("hani2-theme") || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    if (theme === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("hani2-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return [theme, setTheme] as const;
}

export function ThemeButton() {
  const [theme, setTheme] = useTheme();
  const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  const I = theme === "light" ? Sun : theme === "dark" ? Moon : SunMoon;
  return (
    <button className="btn-ghost px-2" onClick={() => setTheme(next)} title={`Theme: ${theme}`} aria-label={`Theme: ${theme}`}>
      <I size={17} />
    </button>
  );
}

function Timer() {
  const n = useStore((s) => s.state?.negotiation);
  const phase = useStore((s) => s.state?.phase);
  const [, tick] = useState(0);
  const now = clockNow();
  const skew = useRef(0);
  useEffect(() => {
    skew.current = isVirtual() ? 0 : n?.server_time ? n.server_time - clockNow() : skew.current;
  }, [n?.server_time]);
  useEffect(() => {
    const t = window.setInterval(() => tick((x) => x + 1), 500);
    return () => window.clearInterval(t);
  }, []);
  if (!n) return null;
  const running = phase === "running";
  const left = n.deadline ? n.deadline - (now + (isVirtual() ? 0 : skew.current)) : null;
  const frac = n.n_steps ? Math.min(1, n.step / n.n_steps) : n.relative_time ?? 0;
  const timeFrac = n.deadline && n.time_limit ? Math.max(0, Math.min(1, 1 - (left ?? 0) / n.time_limit)) : frac;
  const urgent = running && left !== null && left <= 10;
  return (
    <Anchor id="timer" className="flex items-center gap-3">
      <div className="hidden w-28 sm:block" aria-hidden>
        <div className="h-1.5 rounded-full bg-sunken">
          <div className={`h-1.5 rounded-full transition-[width] duration-500 ${urgent ? "bg-bad" : "bg-ink/70"}`} style={{ width: `${Math.max(frac, timeFrac) * 100}%` }} />
        </div>
      </div>
      <div className="tnum text-sm leading-tight">
        <div className={`font-semibold ${urgent ? "text-bad" : ""}`}>{left !== null && running ? clock(left) : running ? "No limit" : "—"}</div>
        <div className="text-[11px] text-muted">
          Round {n.step}
          {n.n_steps ? ` of ${n.n_steps}` : ""}
        </div>
      </div>
    </Anchor>
  );
}

function Menu({ id, button, children }: { id: string; button: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useUiState(`headerMenu.${id}`, false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <div onClick={() => setOpen(!open)}>{button}</div>
      {open && (
        <div className="enter absolute right-0 top-full z-50 mt-1.5 min-w-[13rem] rounded-xl border border-line bg-surface p-1 shadow-pop" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}

const MenuItem = ({ icon: I, children, onClick, active }: any) => (
  <button className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-sunken ${active ? "text-you" : ""}`} onClick={onClick}>
    {I && <I size={15} />}
    {children}
  </button>
);

function PasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [f, setF] = useState({ old: "", new: "", confirm: "" });
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal open={open} onClose={onClose} title="Change password">
      <form
        className="flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault();
          if (f.new !== f.confirm) return setErr("The new passwords do not match.");
          try {
            await api("/api/auth/password", { body: { old: f.old, new: f.new } });
            useStore.getState().pushToast({ message: "Password changed", level: "success" });
            setF({ old: "", new: "", confirm: "" });
            setErr(null);
            onClose();
          } catch (e: any) {
            setErr(e.message);
          }
        }}
      >
        {err && <div className="rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">{err}</div>}
        {(["old", "new", "confirm"] as const).map((k) => (
          <label key={k}>
            <span className="label">{k === "old" ? "Current password" : k === "new" ? "New password" : "Repeat the new password"}</span>
            <input className="field" type="password" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} required />
          </label>
        ))}
        <button className="btn-primary">Change password</button>
      </form>
    </Modal>
  );
}

export function Header({ onSettings, device = "desktop" }: { onSettings: () => void; device?: "desktop" | "tablet" | "phone" }) {
  const st = useStore((s) => s.state);
  const [pw, setPw] = useState(false);
  const assistantOpen = useStore((s) => s.assistantOpen);
  const setAssistant = useStore((s) => s.setAssistantOpen);
  if (!st) return null;
  const ap = st.autopilot;
  const sup = st.support;
  const view = st.layout.view;
  const logout = async () => {
    await api("/api/auth/logout", { body: {} });
    useStore.getState().disconnect();
    navigate("/login");
  };
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-3 sm:px-4">
      <Brand />
      <div className="mx-1 hidden h-6 w-px bg-line md:block" />
      <div className="hidden min-w-0 flex-1 md:block">
        <div className="truncate text-sm font-semibold">{st.scenario?.title ?? "Negotiation"}</div>
        <div className="flex items-center gap-2 truncate text-xs text-muted">
          {st.scenario?.role && <span>You are the {st.scenario.role}</span>}
          <span className={`rounded px-1.5 py-px font-medium ${st.round.practice ? "bg-warn/15 text-warn" : "bg-sunken text-ink"}`}>{st.round.label}</span>
          {st.opponent && (
            <span className="truncate rounded bg-opponent/10 px-1.5 py-px text-opponent" title={st.opponent.type}>
              Opponent: {st.opponent.name}
            </span>
          )}
          {st.webmcp?.enabled && webmcpAvailable() && (
            <span className="rounded bg-good/10 px-1.5 py-px font-medium text-good" title={st.webmcp.actions ? "Browser AI agents can read and negotiate on this page (WebMCP)" : "Browser AI agents can read this page (WebMCP)"}>
              WebMCP
            </span>
          )}
          {st.is_admin && (
            <span className="inline-flex items-center gap-1 rounded bg-bad/10 px-1.5 py-px font-medium text-bad">
              <Shield size={11} /> Admin
            </span>
          )}
        </div>
      </div>
      <div className="flex-1 md:hidden" />
      <Timer />
      <div className="flex items-center gap-1">
        {ap?.allowed && device === "desktop" && (
          <div className="hidden items-center gap-1.5 lg:flex">
            {ap.can_choose && ap.drivers && (
              <select className="field w-36 py-1 text-xs" value={ap.driver ?? ""} onChange={(e) => send({ type: "autopilot", active: !!ap.active, driver: e.target.value })} aria-label="Autopilot driver">
                {ap.drivers.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            )}
            <button
              className={`btn px-2.5 ${ap.active ? "bg-you text-white" : "border border-line text-muted hover:text-ink"}`}
              disabled={!ap.available}
              aria-pressed={!!ap.active}
              onClick={() => send({ type: "autopilot", active: !ap.active })}
              title={ap.available ? "Let an agent negotiate for you" : "Autopilot is not available"}
            >
              <Plane size={15} /> Autopilot
            </button>
          </div>
        )}
        {sup && (
          <button
            className={`btn px-2.5 ${assistantOpen ? "bg-ink text-surface" : "border border-line hover:bg-sunken"} relative`}
            onClick={() => setAssistant(!assistantOpen)}
            aria-pressed={assistantOpen}
          >
            <Bot size={16} />
            <span className="hidden sm:inline">Assistant</span>
            <span className={`absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface ${sup.enabled ? (sup.busy ? "bg-warn" : "bg-good") : "bg-muted"}`} />
          </button>
        )}
        {device !== "phone" && (
        <Menu
          id="layout"
          button={
            <button className="btn-ghost px-2" aria-label="Layout">
              {view === "full" ? <Columns3 size={17} /> : view === "simple" ? <LayoutPanelLeft size={17} /> : <Maximize2 size={17} />}
            </button>
          }
        >
          <div className="px-2.5 pb-1 pt-1.5 text-xs text-muted">Layout</div>
          <MenuItem icon={Columns3} active={view !== "focus"} onClick={() => send({ type: "layout", view: "full" })}>
            {device === "tablet" ? "Show the tools" : "Full: all tool panes"}
          </MenuItem>
          {device === "desktop" && (
          <MenuItem icon={LayoutPanelLeft} active={view === "simple"} onClick={() => send({ type: "layout", view: "simple" })}>
            Simple: one tools area
          </MenuItem>
          )}
          <MenuItem icon={Maximize2} active={view === "focus"} onClick={() => send({ type: "layout", view: "focus" })}>
            Focus: negotiation only
          </MenuItem>
        </Menu>
        )}
        <button className="btn-ghost px-2" onClick={onSettings} aria-label="Settings">
          <Settings2 size={17} />
        </button>
        {device !== "phone" && <ThemeButton />}
        <Menu
          id="account"
          button={
            <button className="btn-ghost gap-1.5 px-2" aria-label="Account">
              <UserRound size={17} />
              <span className="hidden max-w-[8rem] truncate text-sm xl:inline">{st.display_name}</span>
            </button>
          }
        >
          <div className="px-2.5 py-1.5 text-sm">
            <div className="font-medium">{st.display_name}</div>
            <div className="text-xs text-muted">{st.mode === "guest" ? "Playground" : st.user}</div>
          </div>
          {ap?.allowed && device !== "desktop" && (
            <MenuItem icon={Plane} onClick={() => ap.available && send({ type: "autopilot", active: !ap.active })}>
              {ap.active ? "Stop autopilot" : ap.available ? "Start autopilot" : "Autopilot unavailable"}
            </MenuItem>
          )}
          {st.is_admin && (
            <MenuItem icon={Shield} onClick={() => navigate("/admin")}>
              Administration
            </MenuItem>
          )}
          {st.mode === "main" && (
            <MenuItem icon={KeyRound} onClick={() => setPw(true)}>
              Change password
            </MenuItem>
          )}
          {st.mode === "main" && (
            <MenuItem icon={LogOut} onClick={logout}>
              Log out
            </MenuItem>
          )}
        </Menu>
      </div>
      <PasswordDialog open={pw} onClose={() => setPw(false)} />
    </header>
  );
}
