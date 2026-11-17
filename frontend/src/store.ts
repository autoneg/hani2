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
  send: (msg: Record<string, any>) => void;
  setConfirm: (c: ConfirmReq) => void;
  setAssistantOpen: (v: boolean) => void;
  pushToast: (t: Omit<Toast, "id">) => void;
  dropToast: (id: number) => void;
  connect: (sid: string) => void;
  disconnect: () => void;
  patchDraft: (values: Record<string, any>, utility?: number | null) => void;
  patchDraftText: (text: string) => void;
}

let toastId = 1;
let retry = 0;
let wanted: string | null = null;
let pingTimer: number | undefined;

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

  send: (msg) => {
    const ws = get().ws;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  },
  setConfirm: (c) => set({ confirm: c }),
  setAssistantOpen: (v) => set({ assistantOpen: v }),
  setMaximized: (id) => set({ maximized: id }),
  pushToast: (t) => {
    const id = toastId++;
    set((s) => ({ toasts: [...s.toasts.slice(-4), { ...t, id }] }));
    const d = t.duration === undefined || t.duration === null ? (t.level === "error" ? 9000 : 5000) : t.duration;
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
    const old = get().ws;
    if (old) old.close();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}${BASE}/api/ws/${encodeURIComponent(sid)}`);
    set({ ws });
    ws.onopen = () => {
      retry = 0;
      set({ connected: true });
      window.clearInterval(pingTimer);
      pingTimer = window.setInterval(() => get().send({ type: "ping" }), 25000);
    };
    ws.onclose = (ev) => {
      set({ connected: false });
      window.clearInterval(pingTimer);
      if (wanted === sid && ev.code !== 4401 && ev.code !== 4404) {
        retry = Math.min(retry + 1, 6);
        window.setTimeout(() => wanted === sid && get().connect(sid), 400 * 2 ** retry);
      }
      if (ev.code === 4404 || ev.code === 4401) window.dispatchEvent(new CustomEvent("hani-session-lost"));
    };
    ws.onmessage = (ev) => {
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
                  state: { ...s.state, draft: { ...s.state.draft, values: msg.draft, utility: msg.utility } },
                  draftVersion: msg.by_agent ? s.draftVersion + 1 : s.draftVersion,
                }
              : {},
          );
          break;
        case "draft_text":
          set((s) => (s.state ? { state: { ...s.state, draft: { ...s.state.draft, text: msg.text } }, draftVersion: s.draftVersion + 1 } : {}));
          break;
        case "toast":
          get().pushToast({ message: msg.message, level: msg.level, duration: msg.duration, action: msg.action });
          break;
        case "confirm":
          set({ confirm: { kind: msg.kind, message: msg.message } });
          break;
      }
    };
  },
  disconnect: () => {
    wanted = null;
    get().ws?.close();
    set({ ws: null, state: null, toolViews: {}, connected: false });
  },
}));

export const send = (msg: Record<string, any>) => useStore.getState().send(msg);
