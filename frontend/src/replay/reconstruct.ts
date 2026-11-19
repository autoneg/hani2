/* Pure reconstruction of what the participant saw, from a `.hrec` recording.
 * No DOM, no store: a Node script can run it. Ports `diff` / `patch` from
 * `hani2/recording/format.py` and applies server messages exactly as
 * `store.ts` does. */
import { canonical, stateHash } from "../hash";

export { canonical, stateHash };

export type Rec = { t: number; k: string; [key: string]: any };
export interface Header {
  id?: string;
  t0: number;
  created?: string;
  session?: Record<string, any>;
  [key: string]: any;
}

/* ---------------- deltas ---------------- */
const isObj = (v: any) => v !== null && typeof v === "object" && !Array.isArray(v);

export function diff(oldV: any, newV: any): Record<string, any> | null {
  const out: Record<string, any> = {};
  for (const k of Object.keys(newV)) {
    const v = newV[k];
    if (!(k in oldV)) out[k] = { s: v };
    else {
      const o = oldV[k];
      if (canonical(o) === canonical(v)) continue;
      if (isObj(o) && isObj(v)) {
        const d = diff(o, v);
        if (d) out[k] = { o: d };
      } else if (Array.isArray(o) && Array.isArray(v) && v.length > o.length && canonical(v.slice(0, o.length)) === canonical(o)) out[k] = { a: v.slice(o.length) };
      else out[k] = { s: v };
    }
  }
  for (const k of Object.keys(oldV)) if (!(k in newV)) out[k] = { d: 1 };
  return Object.keys(out).length ? out : null;
}

export function patch(old: any, delta: Record<string, any> | null | undefined): any {
  if (!delta) return old;
  const n: Record<string, any> = { ...old };
  for (const k of Object.keys(delta)) {
    const op = delta[k];
    if ("s" in op) n[k] = op.s;
    else if ("a" in op) n[k] = [...(n[k] || []), ...op.a];
    else if ("o" in op) n[k] = patch(isObj(n[k]) ? n[k] : {}, op.o);
    else if ("d" in op) delete n[k];
  }
  return n;
}

/* ---------------- the store, as a pure value ---------------- */
export interface Frame {
  state: any | null;
  toolViews: Record<string, any>;
  draftVersion: number;
  /** last `confirm` message the server sent (used when no telemetry says otherwise) */
  confirmMsg: { kind: string; message?: string | null } | null;
}
export const EMPTY: Frame = { state: null, toolViews: {}, draftVersion: 0, confirmMsg: null };

export interface ServerMsg {
  /** index in this timeline */
  i: number;
  /** time on the recording clock when the server sent it */
  t: number;
  seq: number;
  /** when the browser applied it (its `recv`), else `t`; non-decreasing */
  at: number;
  type: string;
  carry: boolean;
  received: boolean;
  /** state: the full state; tool: the full view object `{id, view, ...}`; others: the message */
  data: any;
  id?: string;
}

/** Applies one server message to a frame, as `ws.onmessage` in `store.ts` does. */
export function applyMsg(f: Frame, m: ServerMsg): Frame {
  const d = m.data;
  switch (m.type) {
    case "state":
      return { ...f, state: d };
    case "tool":
      return { ...f, toolViews: { ...f.toolViews, [m.id as string]: d?.view } };
    case "history":
      return f.state ? { ...f, state: { ...f.state, history: d.items } } : f;
    case "chat":
      return f.state ? { ...f, state: { ...f.state, chat: [...f.state.chat, d.message] } } : f;
    case "draft":
      return f.state
        ? {
            ...f,
            state: { ...f.state, draft: { ...f.state.draft, values: d.draft, utility: d.utility, ...("controls" in d ? { controls: d.controls } : {}) } },
          }
        : f;
    case "draft_text":
      return f.state ? { ...f, state: { ...f.state, draft: { ...f.state.draft, text: d.text } }, draftVersion: f.draftVersion + 1 } : f;
    case "confirm":
      return { ...f, confirmMsg: { kind: d.kind, message: d.message } };
    default:
      return f;
  }
}

/* ---------------- telemetry ---------------- */
export interface Tel {
  t: number;
  type: string;
  p: any[];
}
interface Timed<T> {
  t: number;
  v: T;
}
export interface Viewport {
  t: number;
  w: number;
  h: number;
  dpr: number;
  device: string;
  landscape: boolean;
  theme: string;
}
export interface ClickEv {
  t: number;
  x: number;
  y: number;
  button: number;
  target: Record<string, any>;
}
export interface Checkpoint {
  t: number;
  seq: number;
  hash: string;
}
export interface ToastEv {
  at: number;
  message: string;
  level: string;
  duration: number; // seconds visible
}

/** Index of the last element with `.t <= T` (or -1). */
export function lastBefore(a: { t: number }[], T: number): number {
  let lo = 0,
    hi = a.length - 1,
    r = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (a[mid].t <= T) {
      r = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return r;
}

export interface TelemetryView {
  viewport: Viewport | null;
  pointer: { x: number; y: number; down: boolean } | null;
  clicks: { x: number; y: number; age: number; button: number; target: Record<string, any> }[];
  key: { key: string; age: number } | null;
  scroll: { sel: string; top: number; left: number; t: number }[];
  inputs: { sel: string; value: any; t: number }[];
  ui: Record<string, any>;
  assistantOpen: boolean | null;
  maximized: string | null | undefined;
  confirm: any | undefined;
  focused: boolean;
  visible: boolean;
}

export interface FrameView extends TelemetryView {
  frame: Frame;
  toasts: ToastEv[];
  /** virtual server time (epoch seconds) */
  clock: number;
  msgIndex: number;
}

const KEYFRAME = 200;

export class Replay {
  header: Header;
  events: Rec[];
  t0: number;
  duration: number;
  msgs: ServerMsg[] = [];
  tel: Tel[] = [];
  viewports: Viewport[] = [];
  pointer: Timed<{ x: number; y: number }>[] = [];
  downs: Timed<boolean>[] = [];
  clicks: ClickEv[] = [];
  keys: Timed<string>[] = [];
  focus: Timed<boolean>[] = [];
  vis: Timed<boolean>[] = [];
  scrolls = new Map<string, Timed<[number, number]>[]>();
  inputs = new Map<string, Timed<any>[]>();
  uiKeys = new Map<string, Timed<any>[]>();
  checkpoints: Checkpoint[] = [];
  toastEvs: ToastEv[] = [];
  recv = new Map<number, number>();
  hasTelemetry = false;
  private keyframes: Frame[] = [];

  constructor(header: Header, events: Rec[]) {
    this.header = header;
    this.events = events;
    this.t0 = Number(header?.t0 ?? 0);
    let dur = 0;
    for (const e of events) dur = Math.max(dur, Number(e.t) || 0);
    this.parseTelemetry();
    for (const t of this.tel) dur = Math.max(dur, t.t);
    this.duration = dur;
    this.buildMessages();
  }

  private parseTelemetry() {
    const tel: Tel[] = [];
    for (const e of this.events) {
      if (e.k !== "tel") continue;
      const sent = e.sent == null ? null : Number(e.sent);
      for (const it of e.ev || []) {
        if (!Array.isArray(it) || it.length < 2) continue;
        const ct = it[0];
        const t = sent != null && ct != null ? Number(e.t) + (Number(ct) - sent) / 1000 : Number(e.t);
        tel.push({ t: Math.max(0, t), type: String(it[1]), p: it.slice(2) });
      }
    }
    tel.sort((a, b) => a.t - b.t);
    this.tel = tel;
    this.hasTelemetry = tel.length > 0;
    const push = <T>(m: Map<string, Timed<T>[]>, k: string, t: number, v: T) => {
      let a = m.get(k);
      if (!a) m.set(k, (a = []));
      a.push({ t, v });
    };
    for (const { t, type, p } of tel) {
      switch (type) {
        case "vp":
          this.viewports.push({ t, w: p[0], h: p[1], dpr: p[2], device: p[3], landscape: !!p[4], theme: p[5] });
          break;
        case "mm":
          this.pointer.push({ t, v: { x: p[0], y: p[1] } });
          break;
        case "pd":
          this.pointer.push({ t, v: { x: p[0], y: p[1] } });
          this.downs.push({ t, v: true });
          break;
        case "pu":
          this.pointer.push({ t, v: { x: p[0], y: p[1] } });
          this.downs.push({ t, v: false });
          break;
        case "click":
          this.pointer.push({ t, v: { x: p[0], y: p[1] } });
          this.clicks.push({ t, x: p[0], y: p[1], button: p[2], target: p[3] || {} });
          break;
        case "key":
          this.keys.push({ t, v: String(p[0]) });
          break;
        case "scroll":
          push(this.scrolls, p[0], t, [p[1], p[2]] as [number, number]);
          break;
        case "input":
          push(this.inputs, p[0], t, p[1]);
          break;
        case "ui":
          push(this.uiKeys, p[0], t, p[1]);
          break;
        case "focus":
        case "blur":
          this.focus.push({ t, v: type === "focus" });
          break;
        case "vis":
          this.vis.push({ t, v: p[0] !== "hidden" });
          break;
        case "recv":
          if (!this.recv.has(p[0])) this.recv.set(p[0], t);
          break;
        case "toast":
          this.toastEvs.push({ at: t, message: p[0]?.message ?? "", level: p[0]?.level ?? "info", duration: p[0]?.level === "error" ? 9 : 5 });
          break;
        case "chk":
          this.checkpoints.push({ t, seq: p[0], hash: p[1] });
          break;
      }
    }
  }

  private buildMessages() {
    let cur: any = {};
    const tools: Record<string, any> = {};
    let run = 0;
    let i = 0;
    for (const e of this.events) {
      if (e.k !== "out") continue;
      const type = String(e.m);
      const seq = typeof e.seq === "number" ? e.seq : -1;
      let data: any;
      let id: string | undefined;
      if (type === "state") {
        cur = "full" in e ? e.full : patch(cur, e.delta);
        data = cur;
      } else if (type === "tool") {
        id = String(e.id);
        const v = "full" in e ? e.full : patch(tools[id] || {}, e.delta);
        tools[id] = v;
        data = v;
      } else data = e.msg ?? {};
      const carry = !!e.carry;
      const recvT = this.recv.get(seq);
      run = Math.max(run, recvT ?? Number(e.t) ?? 0);
      this.msgs.push({ i: i++, t: Number(e.t), seq, at: run, type, carry, received: recvT !== undefined, data, id });
      if (type === "toast")
        this.toastEvs.push({
          at: run,
          message: data.message ?? "",
          level: data.level ?? "info",
          duration: data.duration ? data.duration / 1000 : data.level === "error" ? 9 : 5,
        });
    }
    this.toastEvs.sort((a, b) => a.at - b.at);
  }

  /** The frame after applying messages 0..idx (-1: nothing yet). */
  frameAtMsg(idx: number): Frame {
    if (idx < 0) return EMPTY;
    const kf = Math.floor(idx / KEYFRAME);
    // keyframe n is the frame after message n*KEYFRAME
    while (this.keyframes.length <= kf) {
      const n = this.keyframes.length;
      let f = n === 0 ? EMPTY : this.keyframes[n - 1];
      for (let j = n === 0 ? 0 : (n - 1) * KEYFRAME + 1; j <= n * KEYFRAME; j++) f = applyMsg(f, this.msgs[j]);
      this.keyframes.push(f);
    }
    let f = this.keyframes[kf];
    for (let j = kf * KEYFRAME + 1; j <= idx; j++) f = applyMsg(f, this.msgs[j]);
    return f;
  }

  /** Index of the last message the browser had applied by time T. */
  msgIndexAt(T: number): number {
    return this.msgIdx(T);
  }
  private msgIdx(T: number): number {
    const a = this.msgs;
    let lo = 0,
      hi = a.length - 1,
      r = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (a[mid].at <= T) {
        r = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return r;
  }

  /** Last message index whose seq <= `seq` (what the browser had when it hashed). */
  msgIndexForSeq(seq: number): number {
    const a = this.msgs;
    let lo = 0,
      hi = a.length - 1,
      r = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (a[mid].seq <= seq) {
        r = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return r;
  }

  telemetryAt(T: number): TelemetryView {
    const vi = lastBefore(this.viewports, T);
    const pi = lastBefore(this.pointer, T);
    const di = lastBefore(this.downs, T);
    const ki = lastBefore(this.keys, T);
    const fi = lastBefore(this.focus, T);
    const vsi = lastBefore(this.vis, T);
    const scroll: TelemetryView["scroll"] = [];
    this.scrolls.forEach((a, sel) => {
      const i = lastBefore(a, T);
      if (i >= 0) scroll.push({ sel, top: a[i].v[0], left: a[i].v[1], t: a[i].t });
    });
    const inputs: TelemetryView["inputs"] = [];
    this.inputs.forEach((a, sel) => {
      const i = lastBefore(a, T);
      if (i >= 0) inputs.push({ sel, value: a[i].v, t: a[i].t });
    });
    const ui: Record<string, any> = {};
    let assistantOpen: boolean | null = null;
    let maximized: string | null | undefined;
    let confirm: any;
    this.uiKeys.forEach((a, key) => {
      const i = lastBefore(a, T);
      if (i < 0) return;
      const v = a[i].v;
      if (key === "assistantOpen") assistantOpen = !!v;
      else if (key === "maximized") maximized = v ?? null;
      else if (key === "confirm") confirm = v ?? null;
      else if (v !== null && v !== undefined) ui[key] = v;
    });
    // clicks within the last 0.8 s
    const clicks: TelemetryView["clicks"] = [];
    for (let i = lastBefore(this.clicks, T); i >= 0 && T - this.clicks[i].t < 0.8; i--) {
      const c = this.clicks[i];
      clicks.push({ x: c.x, y: c.y, age: T - c.t, button: c.button, target: c.target });
    }
    return {
      viewport: vi >= 0 ? this.viewports[vi] : this.viewports[0] ?? null,
      pointer: pi >= 0 ? { ...this.pointer[pi].v, down: di >= 0 ? this.downs[di].v : false } : null,
      clicks,
      key: ki >= 0 && T - this.keys[ki].t < 0.9 ? { key: this.keys[ki].v, age: T - this.keys[ki].t } : null,
      scroll,
      inputs,
      ui,
      assistantOpen,
      maximized,
      confirm,
      focused: fi >= 0 ? this.focus[fi].v : true,
      visible: vsi >= 0 ? this.vis[vsi].v : true,
    };
  }

  at(T: number): FrameView {
    const idx = this.msgIdx(T);
    const frame = this.frameAtMsg(idx);
    const tv = this.telemetryAt(T);
    const toasts = this.toastEvs.filter((x) => x.at <= T && T < x.at + x.duration).slice(-5);
    return { ...tv, frame, toasts, clock: this.t0 + T, msgIndex: idx };
  }

  /** Resolved values for the store (from the recorded local UI state). */
  storeValues(v: FrameView) {
    return { assistantOpen: v.assistantOpen ?? false, maximized: v.maximized ?? null, confirm: v.confirm ?? null };
  }

  /* ---------- fidelity ---------- */
  verify(): FidelityReport {
    const items: CheckResult[] = [];
    for (const c of this.checkpoints) {
      const idx = this.msgIndexForSeq(c.seq);
      const f = this.frameAtMsg(idx);
      const got = f.state ? stateHash(f.state) : "none";
      const ok = got === c.hash;
      let note: string | undefined;
      let keys: string[] | undefined;
      if (!ok) {
        // does it match a nearby message (the client was a few messages ahead / behind)?
        for (let d = 1; d <= 12 && !note; d++)
          for (const j of [idx + d, idx - d]) {
            if (j < 0 || j >= this.msgs.length) continue;
            const g = this.frameAtMsg(j);
            if (g.state && stateHash(g.state) === c.hash) {
              note = `matches the state after message seq ${this.msgs[j].seq} (${j - idx > 0 ? "+" : ""}${j - idx} messages)`;
              keys = diffKeys(f.state, g.state);
              break;
            }
          }
      }
      items.push({ t: c.t, seq: c.seq, expected: c.hash, got, ok, note, keys, msgIndex: idx });
    }
    const recorded = this.msgs.filter((m) => !m.carry && m.seq > 0);
    const received = recorded.filter((m) => m.received);
    const missing = this.hasTelemetry ? recorded.filter((m) => !m.received).map((m) => m.seq) : [];
    return {
      items,
      matched: items.filter((x) => x.ok).length,
      recorded: recorded.length,
      received: received.length,
      recvEvents: this.recv.size,
      missing,
    };
  }
}

export interface CheckResult {
  t: number;
  seq: number;
  expected: string;
  got: string;
  ok: boolean;
  note?: string;
  keys?: string[];
  msgIndex: number;
}
export interface FidelityReport {
  items: CheckResult[];
  matched: number;
  recorded: number;
  received: number;
  recvEvents: number;
  missing: number[];
}

/** Dotted paths (two levels) at which two states differ. */
export function diffKeys(a: any, b: any, max = 40): string[] {
  const out: string[] = [];
  const walk = (x: any, y: any, path: string, depth: number) => {
    if (out.length >= max) return;
    if (canonical(x) === canonical(y)) return;
    if (depth < 2 && isObj(x) && isObj(y)) {
      for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) walk(x[k], y[k], path ? `${path}.${k}` : k, depth + 1);
    } else out.push(path || "(root)");
  };
  walk(a, b, "", 0);
  return out;
}

export function parseRecording(json: { header: Header; events: Rec[] }): Replay {
  return new Replay(json.header, json.events);
}
