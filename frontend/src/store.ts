import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { BASE } from "./router";
import type { Component, HistoryItem, SessionState, Toast } from "./types";

type ConfirmReq = { kind: "accept" | "end"; message?: string | null } | null;

interface Store {
  state: SessionState | null;
  toolViews: Record<string, Component[] | null>;
  toasts: Toast[];
  connected: boolean;
  confirm: ConfirmReq;
  assistantOpen: boolean;
  /** id of the tool shown enlarged (window or full screen), if any */
  maximized: string | null;
  setMaximized: (id: string | null) => void;
  draftVersion: number;
  ws: WebSocket | null;
  /** sends a message; false when the socket is not open */
  send: (msg: Record<string, any>) => boolean;
  /** Local UI state that changes what is on screen (see `useUiState`); recorded and replayed. */
  ui: Record<string, any>;
  setUi: (key: string, value: any) => void;
  clearUi: (key: string) => void;
  /** true inside the replay frame: components must not change recorded state by themselves */
  replay: boolean;
  setConfirm: (c: ConfirmReq) => void;
  setAssistantOpen: (v: boolean) => void;
  pushToast: (t: Omit<Toast, "id">, fromServer?: boolean) => void;
  dropToast: (id: number) => void;
  connect: (sid: string) => void;
  disconnect: () => void;
  patchDraft: (values: Record<string, any>, utility?: number | null) => void;
  patchDraftText: (text: string) => void;
}

/** Observers the live telemetry attaches (the store does not import it). */
export const hooks: {
  recv?: (seq: number, type: string) => void;
  toast?: (t: { message: string; level: string }) => void;
} = {};

let toastId = 1;
let retry = 0;
let wanted: string | null = null;
let pingTimer: number | undefined;
let retryTimer: number | undefined;

/* Tool views arrive in bursts; apply them together once per frame so a burst
 * of updates causes one re-render instead of many. */
let pendingViews: Record<string, any> = {};
let viewFrame = 0;
function queueToolView(id: string, view: any) {
  pendingViews[id] = view;
  if (viewFrame) return;
  const flush = () => {
    viewFrame = 0;
    const batch = pendingViews;
    pendingViews = {};
    useStore.setState((s) => ({ toolViews: { ...s.toolViews, ...batch } }));
  };
  viewFrame = typeof requestAnimationFrame === "function" && document.visibilityState === "visible"
    ? requestAnimationFrame(flush)
    : (setTimeout(flush, 16) as unknown as number);
}

export const useStore = create<Store>((set, get) => ({
  state: null,
  toolViews: {},
  toasts: [],
  connected: false,
  confirm: null,
  assistantOpen: false,
  maximized: null,
  draftVersion: 0,
  ws: null,
  ui: {},
  replay: false,
  setUi: (key, value) => {
    if (get().replay) return;
    set((s) => (Object.is(s.ui[key], value) ? {} : { ui: { ...s.ui, [key]: value } }));
  },
  clearUi: (key) => {
    if (get().replay) return;
    set((s) => {
      if (!(key in s.ui)) return {};
      const { [key]: _x, ...rest } = s.ui;
      return { ui: rest };
    });
  },

  send: (msg) => {
    const ws = get().ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
      return true;
    }
    return false;
  },
  setConfirm: (c) => set({ confirm: c }),
  setAssistantOpen: (v) => set({ assistantOpen: v }),
  setMaximized: (id) => set({ maximized: id }),
  pushToast: (t, fromServer = false) => {
    if (!fromServer) hooks.toast?.({ message: t.message, level: t.level });
    const id = toastId++;
    set((s) => ({ toasts: [...s.toasts.slice(-4), { ...t, id }] }));
    const base = get().state?.interface?.toast_ms ?? 5000;
    const d = t.duration === undefined || t.duration === null ? (t.level === "error" && base > 0 ? Math.max(base, 9000) : base) : t.duration;
    if (d > 0) window.setTimeout(() => get().dropToast(id), d);
  },
  dropToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),

  patchDraft: (values, utility) =>
    set((s) =>
      s.state
        ? {
            state: {
              ...s.state,
              draft: { ...s.state.draft, values: { ...s.state.draft.values, ...values }, utility: utility ?? s.state.draft.utility },
            },
          }
        : {},
    ),
  patchDraftText: (text) => set((s) => (s.state ? { state: { ...s.state, draft: { ...s.state.draft, text } } } : {})),

  connect: (sid) => {
    wanted = sid;
    window.clearTimeout(retryTimer); // a pending retry from an earlier socket must not replace this one
    const old = get().ws;
    if (old) {
      old.onclose = old.onmessage = old.onopen = null; // its late events are not about this socket
      old.close();
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}${BASE}/api/ws/${encodeURIComponent(sid)}`);
    set({ ws });
    ws.onopen = () => {
      if (get().ws !== ws) return;
      retry = 0;
      set({ connected: true });
      window.clearInterval(pingTimer);
      pingTimer = window.setInterval(() => get().send({ type: "ping" }), 25000);
    };
    ws.onclose = (ev) => {
      if (get().ws !== ws) return;
      set({ connected: false });
      window.clearInterval(pingTimer);
      if (wanted === sid && ev.code !== 4401 && ev.code !== 4404) {
        retry = Math.min(retry + 1, 6);
        window.clearTimeout(retryTimer);
        retryTimer = window.setTimeout(() => wanted === sid && get().connect(sid), 400 * 2 ** retry);
      }
      if (ev.code === 4404 || ev.code === 4401) window.dispatchEvent(new CustomEvent("hani-session-lost"));
    };
    ws.onmessage = (ev) => {
      if (get().ws !== ws) return;
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch (e) {
        console.error("hani2: could not parse a server message", e);
        return;
      }
      switch (msg.type) {
        case "state":
          set({ state: msg.state });
          break;
        case "tool":
          queueToolView(msg.id, msg.view);
          break;
        case "history":
          set((s) => (s.state ? { state: { ...s.state, history: msg.items as HistoryItem[] } } : {}));
          break;
        case "chat":
          set((s) => (s.state ? { state: { ...s.state, chat: [...s.state.chat, msg.message] } } : {}));
          break;
        case "draft":
          set((s) =>
            s.state
              ? {
                  state: {
                    ...s.state,
                    draft: { ...s.state.draft, values: msg.draft, utility: msg.utility, ...("controls" in msg ? { controls: msg.controls } : {}) },
                  },
                  draftVersion: msg.by_agent ? s.draftVersion + 1 : s.draftVersion,
                }
              : {},
          );
          break;
        case "draft_text":
          set((s) => (s.state ? { state: { ...s.state, draft: { ...s.state.draft, text: msg.text } }, draftVersion: s.draftVersion + 1 } : {}));
          break;
        case "toast":
          get().pushToast({ message: msg.message, level: msg.level, duration: msg.duration, action: msg.action, source: msg.source }, true);
          break;
        case "confirm":
          set({ confirm: { kind: msg.kind, message: msg.message } });
          break;
      }
      if (typeof msg._seq === "number") hooks.recv?.(msg._seq, String(msg.type));
    };
  },
  disconnect: () => {
    wanted = null;
    window.clearTimeout(retryTimer);
    window.clearInterval(pingTimer);
    get().ws?.close();
    set({ ws: null, state: null, toolViews: {}, connected: false, ui: {} });
  },
}));

export const send = (msg: Record<string, any>) => useStore.getState().send(msg);

const UNSET = Symbol("unset");

/** Drop-in for `useState` whose value lives in the store, so it is recorded
 *  (`["ui", key, value]`) and can be replayed. The key must be unique per
 *  on-screen instance. Without a key it is plain local state. Like
 *  `useState`, the value resets when the component unmounts. */
export function useUiState<T>(key: string | undefined, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const init = useRef(initial);
  const lastKey = useRef(key);
  if (lastKey.current !== key) {
    // a new key is a new piece of state: it starts from the current initial value
    lastKey.current = key;
    init.current = initial;
  }
  const [local, setLocal] = useState<T>(initial);
  const stored = useStore((s) => (key !== undefined && key in s.ui ? s.ui[key] : UNSET)) as T | typeof UNSET;
  const value = key === undefined ? local : stored === UNSET ? init.current : stored;
  const cur = useRef(value);
  cur.current = value;
  const setValue = useCallback(
    (x: T | ((p: T) => T)) => {
      const next = typeof x === "function" ? (x as (p: T) => T)(cur.current) : x;
      cur.current = next;
      if (key === undefined) setLocal(next);
      else useStore.getState().setUi(key, next);
    },
    [key],
  );
  useEffect(() => {
    if (key === undefined) return;
    return () => useStore.getState().clearUi(key);
  }, [key]);
  return [value, setValue];
}
