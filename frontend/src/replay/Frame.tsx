import { useEffect, useState } from "react";
import { useStore } from "../store";
import { setVirtualNow } from "../clock";
import { NegotiateBody } from "../negotiate/NegotiatePage";
import type { Device } from "../device";

/** What the player sends (all fields optional: only what changed). */
export interface ReplayMessage {
  type: "hani2-replay";
  state?: any;
  toolViews?: Record<string, any>;
  draftVersion?: number;
  ui?: Record<string, any>;
  assistantOpen?: boolean;
  maximized?: string | null;
  confirm?: any;
  toasts?: { message: string; level: string }[];
  clock?: number;
  theme?: string;
  device?: Device;
  landscape?: boolean;
  scroll?: { sel: string; top: number; left: number; t: number }[];
  inputs?: { sel: string; value: any; t: number }[];
}

const appliedScroll = new WeakMap<Element, number>();
const appliedInput = new WeakMap<Element, number>();
const WINDOW_T = { t: -1 };

function applyScroll(list: NonNullable<ReplayMessage["scroll"]>) {
  for (const s of list) {
    if (s.sel === "window") {
      if (WINDOW_T.t !== s.t) {
        WINDOW_T.t = s.t;
        window.scrollTo({ top: s.top, left: s.left, behavior: "instant" as ScrollBehavior });
      }
      continue;
    }
    let el: Element | null = null;
    try {
      el = document.querySelector(s.sel);
    } catch {
      /* bad selector */
    }
    if (!el || appliedScroll.get(el) === s.t) continue;
    appliedScroll.set(el, s.t);
    el.scrollTo({ top: s.top, left: s.left, behavior: "instant" as ScrollBehavior });
  }
}

function applyInputs(list: NonNullable<ReplayMessage["inputs"]>) {
  for (const s of list) {
    let el: any = null;
    try {
      el = document.querySelector(s.sel);
    } catch {
      /* bad selector */
    }
    if (!el || appliedInput.get(el) === s.t) continue;
    appliedInput.set(el, s.t);
    if (el.type === "checkbox" || el.type === "radio") {
      if (el.checked !== !!s.value) el.click();
      continue;
    }
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter && el.value !== String(s.value ?? "")) {
      setter.call(el, String(s.value ?? ""));
      el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
    }
  }
}

let toastN = 1;

/** The negotiation screen driven entirely by the replay player (no socket, no session). */
export function ReplayFrame() {
  const [lay, setLay] = useState<{ device: Device; landscape: boolean }>({ device: "desktop", landscape: true });
  const has = useStore((s) => !!s.state);

  useEffect(() => {
    useStore.setState({ replay: true, ws: null, connected: false });
    document.documentElement.dataset.replay = "1";
    document.body.style.overflow = "hidden";
    const on = (ev: MessageEvent) => {
      if (ev.origin !== location.origin) return;
      const m = ev.data as ReplayMessage;
      if (!m || m.type !== "hani2-replay") return;
      if (m.clock !== undefined) setVirtualNow(m.clock);
      if (m.theme) document.documentElement.setAttribute("data-theme", m.theme);
      const patch: Record<string, any> = {};
      for (const k of ["state", "toolViews", "draftVersion", "ui", "assistantOpen", "maximized", "confirm"] as const) if (m[k] !== undefined) patch[k] = m[k];
      if ("confirm" in m) patch.confirm = m.confirm ?? null;
      if ("maximized" in m) patch.maximized = m.maximized ?? null;
      if (m.toasts) patch.toasts = m.toasts.map((t) => ({ ...t, id: toastN++ }));
      if (Object.keys(patch).length) useStore.setState(patch);
      if (m.device) {
        document.documentElement.dataset.device = m.device;
        setLay((l) => (l.device === m.device && l.landscape === !!m.landscape ? l : { device: m.device!, landscape: !!m.landscape }));
      }
      if (m.scroll || m.inputs)
        for (const delay of [0, 80, 250])
          window.setTimeout(() => {
            if (m.inputs) applyInputs(m.inputs);
            if (m.scroll) applyScroll(m.scroll);
          }, delay);
    };
    window.addEventListener("message", on);
    window.parent.postMessage({ type: "hani2-replay-ready" }, location.origin);
    return () => {
      window.removeEventListener("message", on);
      setVirtualNow(null);
      useStore.setState({ replay: false });
    };
  }, []);

  if (!has) return <div className="flex h-screen items-center justify-center text-sm text-muted">Waiting for the recording…</div>;
  return <NegotiateBody device={lay.device} landscape={lay.landscape} live={false} />;
}
