/* Client telemetry for session recordings: pointer, clicks, keys, scrolling,
 * inputs, focus, viewport, local UI state and checkpoints. Events are buffered
 * and sent to the server (`{type: "telemetry"}`), which writes them into the
 * recording. Event tuples are `[Date.now(), type, ...payload]`. */
import { stateHash } from "./hash";
import { hooks, useStore } from "./store";

export { canonical, fnv1a, stateHash } from "./hash";

type Ev = any[];
const MAX_BUFFER = 20000;
const CHUNK = 4000; // the server keeps at most 5000 events per message

let buf: Ev[] = [];
let running = false;
let cleanup: (() => void) | null = null;
let lastSeq = 0;
/* true once the server shows it is recording (its messages carry `_seq`); until
 * then nothing is sent, so with recording off nothing leaves the browser */
let recorded = false;
let device: { device: string; landscape: boolean } = { device: "desktop", landscape: true };
let lastVp = "";

function push(...e: any[]) {
  if (!running) return;
  buf.push([Date.now(), ...e]);
  if (buf.length > MAX_BUFFER) buf.splice(0, buf.length - MAX_BUFFER);
}

export function flush() {
  if (!buf.length || !recorded) return;
  const st = useStore.getState();
  if (!st.connected || !st.ws || st.ws.readyState !== WebSocket.OPEN) return;
  while (buf.length) {
    const chunk = buf.slice(0, CHUNK);
    if (!st.send({ type: "telemetry", sent: Date.now(), events: chunk })) return;
    buf.splice(0, chunk.length);
  }
}

/* ---------- selectors ---------- */
const esc = (s: string) => (window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&"));
const unique = (s: string) => {
  try {
    return document.querySelectorAll(s).length === 1;
  } catch {
    return false;
  }
};

function direct(el: Element): string | null {
  const tag = el.tagName.toLowerCase();
  const a = el.getAttribute("data-anchor");
  if (a) {
    const s = `[data-anchor="${esc(a)}"]`;
    if (unique(s)) return s;
  }
  if (el.id) {
    const s = `#${esc(el.id)}`;
    if (unique(s)) return s;
  }
  const l = el.getAttribute("aria-label");
  if (l) {
    const s = `${tag}[aria-label="${esc(l)}"]`;
    if (unique(s)) return s;
  }
  return null;
}

/** A selector that resolves to `el` with `document.querySelector`. */
export function selector(t: EventTarget | null): string {
  if (t === document || t === window || t === document.documentElement) return "window";
  const el = t as Element;
  if (!el || !el.tagName) return "window";
  const parts: string[] = [];
  let cur: Element | null = el;
  for (let depth = 0; cur && cur !== document.body && cur !== document.documentElement && depth < 12; depth++) {
    const d = direct(cur);
    if (d) {
      parts.unshift(d);
      return parts.join(" > ");
    }
    const tag = cur.tagName.toLowerCase();
    const same = cur.parentElement ? Array.from(cur.parentElement.children).filter((c) => c.tagName === cur!.tagName) : [];
    parts.unshift(same.length > 1 ? `${tag}:nth-of-type(${same.indexOf(cur) + 1})` : tag);
    cur = cur.parentElement;
  }
  return "body > " + parts.join(" > ");
}

const INTERACTIVE = "button,a,[role=button],input,select,textarea,label,summary,[data-anchor]";
function describe(t: EventTarget | null) {
  const raw = t as Element | null;
  if (!raw || !raw.tagName) return { sel: "window", tag: "window" };
  const el = (raw.closest?.(INTERACTIVE) as Element | null) ?? raw;
  const out: Record<string, any> = { sel: selector(el), tag: el.tagName.toLowerCase() };
  if (el.id) out.id = el.id;
  const label = el.getAttribute("aria-label") || el.getAttribute("title");
  if (label) out.label = label.slice(0, 60);
  const text = ((el as HTMLElement).innerText || "").trim().replace(/\s+/g, " ");
  if (text && (el as HTMLInputElement).type !== "password") out.text = text.slice(0, 60);
  const anchor = el.closest("[data-anchor]")?.getAttribute("data-anchor");
  if (anchor) out.anchor = anchor;
  return out;
}

const isField = (el: any): el is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement =>
  !!el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
const isText = (el: any) => isField(el) && !/^(checkbox|radio|range|button|submit|file|color)$/.test((el as any).type || "");
const isSecret = (el: any) => isField(el) && (el as any).type === "password";

export const resolvedTheme = () => {
  const t = document.documentElement.getAttribute("data-theme");
  if (t === "dark" || t === "light") return t;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

function viewport() {
  const vp = [window.innerWidth, window.innerHeight, window.devicePixelRatio || 1, device.device, device.landscape, resolvedTheme()];
  const k = JSON.stringify(vp);
  if (k === lastVp) return;
  lastVp = k;
  push("vp", ...vp);
}

/** The layout the page is using (from `useDevice`). */
export function setDevice(d: string, landscape: boolean) {
  device = { device: d, landscape };
  if (running) viewport();
}

function uiSnapshot() {
  const s = useStore.getState();
  for (const [k, v] of Object.entries(s.ui)) push("ui", k, v);
  push("ui", "assistantOpen", s.assistantOpen);
  push("ui", "maximized", s.maximized);
  push("ui", "confirm", s.confirm);
}

function checkpoint() {
  const s = useStore.getState().state;
  if (!s) return;
  push("chk", lastSeq, stateHash(s));
}

export function start() {
  if (running) return;
  running = true;
  buf = [];
  lastSeq = 0;
  recorded = false;
  lastVp = "";
  const off: (() => void)[] = [];
  const on = (t: EventTarget, ev: string, fn: (e: any) => void, capture = true) => {
    t.addEventListener(ev, fn, { capture, passive: true });
    off.push(() => t.removeEventListener(ev, fn, { capture }));
  };

  viewport();
  push(document.hasFocus() ? "focus" : "blur");
  push("vis", document.visibilityState);

  /* pointer */
  let lastMove = 0;
  let pos: [number, number] | null = null;
  let sentPos: [number, number] | null = null;
  const emitMove = () => {
    if (pos && (!sentPos || sentPos[0] !== pos[0] || sentPos[1] !== pos[1])) {
      push("mm", pos[0], pos[1]);
      sentPos = [pos[0], pos[1]];
    }
  };
  let moveTimer = 0;
  on(document, "pointermove", (e: PointerEvent) => {
    pos = [Math.round(e.clientX), Math.round(e.clientY)];
    const t = performance.now();
    if (t - lastMove >= 40) {
      lastMove = t;
      emitMove();
    } else if (!moveTimer) {
      moveTimer = window.setTimeout(() => {
        moveTimer = 0;
        lastMove = performance.now();
        emitMove();
      }, 40);
    }
  });
  on(document, "pointerdown", (e: PointerEvent) => {
    pos = [Math.round(e.clientX), Math.round(e.clientY)];
    emitMove();
    push("pd", pos[0], pos[1], e.button, e.pointerType);
  });
  on(document, "pointerup", (e: PointerEvent) => {
    push("pu", Math.round(e.clientX), Math.round(e.clientY), e.button);
  });
  on(document, "click", (e: MouseEvent) => {
    pos = [Math.round(e.clientX), Math.round(e.clientY)];
    emitMove();
    push("click", pos[0], pos[1], e.button, describe(e.target));
  });

  /* keys */
  on(document, "keydown", (e: KeyboardEvent) => {
    if (isSecret(e.target)) return;
    const mod = e.ctrlKey || e.metaKey || e.altKey;
    let key: string;
    if (e.key.length === 1 && !mod && isText(e.target)) key = "char";
    else {
      const pre = (e.ctrlKey ? "Ctrl+" : "") + (e.metaKey ? "Meta+" : "") + (e.altKey ? "Alt+" : "") + (mod && e.shiftKey ? "Shift+" : "");
      key = pre + e.key;
    }
    push("key", key, selector(e.target));
  });

  /* inputs (throttled per element, trailing) */
  const inputTimers = new Map<Element, number>();
  const inputNow = (el: any) => {
    const value = el.type === "checkbox" || el.type === "radio" ? !!el.checked : String(el.value ?? "").slice(0, 2000);
    push("input", selector(el), value);
  };
  const onInput = (e: Event) => {
    const el = e.target as any;
    if (!isField(el) || isSecret(el) || (el as any).type === "file") return;
    if (inputTimers.has(el)) return;
    inputTimers.set(
      el,
      window.setTimeout(() => {
        inputTimers.delete(el);
        inputNow(el);
      }, 150),
    );
  };
  on(document, "input", onInput);
  on(document, "change", (e) => {
    const el = e.target as any;
    if (!isField(el) || isSecret(el) || (el as any).type === "file") return;
    const t = inputTimers.get(el);
    if (t) window.clearTimeout(t);
    inputTimers.delete(el);
    inputNow(el);
  });

  /* scroll (throttled per target, trailing) */
  const scrollTimers = new Map<EventTarget, number>();
  on(document, "scroll", (e: Event) => {
    const t = e.target as EventTarget;
    if (scrollTimers.has(t)) return;
    scrollTimers.set(
      t,
      window.setTimeout(() => {
        scrollTimers.delete(t);
        if (t === document) push("scroll", "window", Math.round(window.scrollY), Math.round(window.scrollX));
        else if ((t as Element).isConnected) push("scroll", selector(t), Math.round((t as Element).scrollTop), Math.round((t as Element).scrollLeft));
      }, 100),
    );
  });

  /* focus / visibility / viewport */
  on(window, "focus", () => push("focus"), false);
  on(window, "blur", () => push("blur"), false);
  on(document, "visibilitychange", () => {
    push("vis", document.visibilityState);
    if (document.visibilityState === "hidden") flush();
  }, false);
  on(window, "pagehide", flush, false);
  let rz = 0;
  const onResize = () => {
    window.clearTimeout(rz);
    rz = window.setTimeout(viewport, 150);
  };
  on(window, "resize", onResize, false);
  on(window, "orientationchange", onResize, false);
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (mq) {
    mq.addEventListener("change", viewport);
    off.push(() => mq.removeEventListener("change", viewport));
  }
  const mo = new MutationObserver(viewport);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  off.push(() => mo.disconnect());

  /* store: received messages, local ui state, toasts, checkpoints */
  let chkTimer = 0;
  hooks.recv = (seq, type) => {
    recorded = true;
    lastSeq = seq;
    push("recv", seq, type);
    if (type === "state") {
      window.clearTimeout(chkTimer);
      chkTimer = window.setTimeout(checkpoint, 300);
    }
  };
  hooks.toast = (t) => push("toast", t);
  let lastTitle: string | undefined;
  const unsub = useStore.subscribe((s, p) => {
    if (s.ui !== p.ui) {
      for (const k of new Set([...Object.keys(s.ui), ...Object.keys(p.ui)])) if (!Object.is(s.ui[k], p.ui[k])) push("ui", k, k in s.ui ? s.ui[k] : null);
    }
    if (s.assistantOpen !== p.assistantOpen) push("ui", "assistantOpen", s.assistantOpen);
    if (s.maximized !== p.maximized) push("ui", "maximized", s.maximized);
    if (s.confirm !== p.confirm) push("ui", "confirm", s.confirm);
    const title = s.state?.scenario?.name;
    if (s.state && title !== lastTitle) {
      lastTitle = title; // a new negotiation starts a new recording: repeat what is on screen
      uiSnapshot();
    }
  });
  off.push(unsub);

  const timers = [
    window.setInterval(flush, 1000),
    window.setInterval(checkpoint, 3000),
    window.setInterval(uiSnapshot, 10000),
  ];
  cleanup = () => {
    timers.forEach((t) => window.clearInterval(t));
    window.clearTimeout(chkTimer);
    window.clearTimeout(moveTimer);
    inputTimers.forEach((t) => window.clearTimeout(t));
    scrollTimers.forEach((t) => window.clearTimeout(t));
    off.forEach((f) => f());
    hooks.recv = undefined;
    hooks.toast = undefined;
  };
}

export function stop() {
  if (!running) return;
  flush();
  running = false;
  cleanup?.();
  cleanup = null;
  buf = [];
}
