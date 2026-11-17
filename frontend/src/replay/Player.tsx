import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronsRight, Loader2, Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { api } from "../api";
import { withBase } from "../router";
import { fmtTime } from "./csv";
import type { RecInfo } from "./Library";
import { EventsPanel, FidelityPanel, InfoPanel, MetricsPanel } from "./Panels";
import { parseRecording, type FrameView, type Replay } from "./reconstruct";
import { buildTimeline, COLOR, type TimelineItem } from "./summary";

const SPEEDS = [0.5, 1, 2, 4, 8];

/* ---------------- the cursor, ripples and key badge, over the frame ---------------- */
function Overlay({ fv, w, h, scale }: { fv: FrameView; w: number; h: number; scale: number }) {
  const inv = `scale(${1 / scale})`;
  const p = fv.pointer;
  return (
    <div className="pointer-events-none absolute left-0 top-0 overflow-hidden" style={{ width: w, height: h, transform: `scale(${scale})`, transformOrigin: "0 0" }}>
      {fv.clicks.map((c, i) => (
        <div
          key={i}
          className="absolute rounded-full border-2 border-you"
          style={{
            left: c.x - (8 + (c.age / 0.8) * 26) / scale,
            top: c.y - (8 + (c.age / 0.8) * 26) / scale,
            width: (16 + (c.age / 0.8) * 52) / scale,
            height: (16 + (c.age / 0.8) * 52) / scale,
            opacity: Math.max(0, 1 - c.age / 0.8),
            background: "rgb(var(--you) / 0.15)",
          }}
        />
      ))}
      {p && (
        <div className="absolute" style={{ left: p.x, top: p.y, transform: inv, transformOrigin: "0 0" }}>
          {p.down && <div className="absolute -left-3 -top-3 h-6 w-6 rounded-full bg-you/30 ring-2 ring-you" />}
          <svg width="22" height="22" viewBox="0 0 24 24" className="absolute left-0 top-0 drop-shadow" style={{ filter: "drop-shadow(0 1px 1px rgba(0,0,0,.45))" }}>
            <path d="M3 2l7 19 3-8 8-3z" fill={p.down ? "rgb(var(--you))" : "#fff"} stroke="#111" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
        </div>
      )}
      {fv.key && (
        <div className="absolute bottom-2 left-2" style={{ transform: inv, transformOrigin: "0 100%", opacity: Math.max(0, 1 - fv.key.age / 0.9) }}>
          <span className="rounded-md bg-ink/85 px-2 py-1 font-mono text-xs text-surface shadow-pop">⌨ {fv.key.key}</span>
        </div>
      )}
      {(!fv.focused || !fv.visible) && (
        <div className="absolute right-2 top-2" style={{ transform: inv, transformOrigin: "100% 0" }}>
          <span className="rounded-md bg-ink/80 px-2 py-1 text-xs text-surface">{!fv.visible ? "Tab hidden" : "Window not focused"}</span>
        </div>
      )}
    </div>
  );
}

/* ---------------- the frame (an iframe driven by postMessage) ---------------- */
function Stage({ replay, fv, w, h, playing }: { replay: Replay; fv: FrameView; w: number; h: number; playing: boolean }) {
  const area = useRef<HTMLDivElement>(null);
  const iframe = useRef<HTMLIFrameElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const [ready, setReady] = useState(false);
  const sent = useRef<Record<string, any>>({});

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    const on = (ev: MessageEvent) => {
      if (ev.origin !== location.origin || ev.source !== iframe.current?.contentWindow) return;
      if (ev.data?.type === "hani2-replay-ready") {
        sent.current = {};
        setReady(true);
      }
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, []);

  useEffect(() => {
    const win = iframe.current?.contentWindow;
    if (!win || !ready) return;
    const sv = replay.storeValues(fv);
    const m: Record<string, any> = { type: "hani2-replay", clock: fv.clock };
    const L = sent.current;
    const js = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b);
    const chg = (k: string, v: any, same: (a: any, b: any) => boolean = Object.is) => {
      if (!(k in L) || !same(L[k], v)) {
        L[k] = v;
        m[k] = v;
      }
    };
    chg("state", fv.frame.state);
    chg("toolViews", fv.frame.toolViews);
    chg("draftVersion", fv.frame.draftVersion);
    chg("ui", fv.ui, js);
    chg("assistantOpen", sv.assistantOpen);
    chg("maximized", sv.maximized);
    chg("confirm", sv.confirm, js);
    chg("toasts", fv.toasts.map((t) => ({ message: t.message, level: t.level })), js);
    chg("theme", fv.viewport?.theme ?? "light");
    chg("device", fv.viewport?.device ?? "desktop");
    chg("landscape", fv.viewport?.landscape ?? true);
    chg("scroll", fv.scroll, js);
    chg("inputs", fv.inputs, js);
    win.postMessage(m, location.origin);
  }, [fv, ready, replay]);

  const scale = Math.max(0.05, Math.min((size.w - 16) / w, (size.h - 16) / h, 1.25));
  return (
    <div ref={area} className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-sunken">
      <div className="relative shrink-0 overflow-hidden rounded-md border border-line bg-paper shadow-pop" style={{ width: w * scale, height: h * scale }}>
        <iframe
          ref={iframe}
          title="Replay"
          src={withBase("/replay/frame")}
          style={{ width: w, height: h, transform: `scale(${scale})`, transformOrigin: "0 0", pointerEvents: "none", border: 0 }}
        />
        <Overlay fv={fv} w={w} h={h} scale={scale} />
      </div>
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-muted">
          <Loader2 size={16} className="animate-spin" /> Loading the frame…
        </div>
      )}
      <div className="absolute bottom-1 right-2 text-[10px] text-muted">
        {w}×{h} · {Math.round(scale * 100)}% {playing ? "" : "· paused"}
      </div>
    </div>
  );
}

/* ---------------- the scrubber ---------------- */
function Scrubber({ T, duration, items, onSeek }: { T: number; duration: number; items: TimelineItem[]; onSeek: (t: number) => void }) {
  const marks = useMemo(() => {
    const coarse = items.filter((i) => i.kind !== "system" && i.kind !== "input");
    const drawn = new Set<string>();
    return coarse.filter((i) => {
      const k = `${i.kind}:${Math.round((i.t / Math.max(1, duration)) * 600)}`;
      if (drawn.has(k)) return false;
      drawn.add(k);
      return true;
    });
  }, [items, duration]);
  return (
    <div className="relative min-w-0 flex-1">
      <div className="pointer-events-none absolute inset-x-[7px] top-0 h-4" aria-hidden>
        {marks.map((m, i) => (
          <span
            key={i}
            className="absolute rounded-sm"
            style={{
              left: `${(m.t / Math.max(0.001, duration)) * 100}%`,
              width: 2,
              top: m.kind === "click" ? 8 : 0,
              height: m.kind === "click" ? 6 : 14,
              background: COLOR[m.kind],
              opacity: m.kind === "click" ? 0.7 : 1,
            }}
            title={`${fmtTime(m.t)} ${m.text}`}
          />
        ))}
      </div>
      <input
        type="range"
        className="mt-4 block w-full accent-[rgb(var(--you))]"
        min={0}
        max={duration}
        step="any"
        value={Math.min(T, duration)}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Timeline"
      />
    </div>
  );
}

type Tab = "events" | "metrics" | "fidelity" | "info";

export function Player({ rkey }: { rkey: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<RecInfo | null>(null);
  useEffect(() => {
    setData(null);
    setError(null);
    api(`/api/replay/recording?key=${encodeURIComponent(rkey)}`)
      .then(setData)
      .catch((e) => setError(e.message));
    api<{ recordings: RecInfo[] }>("/api/replay/recordings?all=true")
      .then((r) => setMeta(r.recordings.find((x) => x.key === rkey) ?? null))
      .catch(() => {});
  }, [rkey]);
  const replay = useMemo(() => {
    if (!data) return null;
    try {
      return parseRecording(data);
    } catch (e: any) {
      setError(`This recording could not be read: ${e.message}`);
      return null;
    }
  }, [data]);
  if (error) return <div className="p-6 text-sm text-bad">{error}</div>;
  if (!replay)
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted">
        <Loader2 size={16} className="animate-spin" /> Loading the recording…
      </div>
    );
  return <PlayerView replay={replay} rkey={rkey} meta={meta} />;
}

function PlayerView({ replay, rkey, meta }: { replay: Replay; rkey: string; meta: RecInfo | null }) {
  const duration = Math.max(1, replay.duration);
  const [T, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [skipIdle, setSkipIdle] = useState(false);
  const [tab, setTab] = useState<Tab>("events");
  const tRef = useRef(0);
  const items = useMemo(() => buildTimeline(replay), [replay]);
  const actions = useMemo(() => items.filter((i) => i.action), [items]);
  const activity = useMemo(() => {
    const a = [...replay.tel.map((t) => t.t), ...replay.msgs.map((m) => m.at)].sort((x, y) => x - y);
    return a;
  }, [replay]);

  const seek = useCallback(
    (t: number) => {
      const v = Math.max(0, Math.min(duration, t));
      tRef.current = v;
      setT(v);
    },
    [duration],
  );

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    let lastRender = 0;
    const step = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000);
      last = now;
      let t = tRef.current + dt * speed;
      if (skipIdle) {
        let lo = 0,
          hi = activity.length - 1,
          nx = duration;
        while (lo <= hi) {
          const mid = (lo + hi) >> 1;
          if (activity[mid] > t) {
            nx = activity[mid];
            hi = mid - 1;
          } else lo = mid + 1;
        }
        if (nx - t > 3) t = nx - 0.6;
      }
      if (t >= duration) {
        t = duration;
        setPlaying(false);
      }
      tRef.current = t;
      if (now - lastRender > 33 || t >= duration) {
        lastRender = now;
        setT(t);
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, skipIdle, activity, duration]);

  const toggle = () => {
    if (!playing && tRef.current >= duration) seek(0);
    setPlaying((p) => !p);
  };
  const next = () => {
    const a = actions.find((i) => i.t > tRef.current + 0.05);
    seek(a ? a.t : duration);
  };
  const prev = () => {
    const a = [...actions].reverse().find((i) => i.t < tRef.current - 0.6);
    seek(a ? a.t : 0);
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) && (el as HTMLInputElement).type !== "range") return;
      if (e.key === " ") {
        e.preventDefault();
        toggle();
      } else if (e.key === "ArrowRight") seek(tRef.current + (e.shiftKey ? 30 : 5));
      else if (e.key === "ArrowLeft") seek(tRef.current - (e.shiftKey ? 30 : 5));
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  const fv = useMemo(() => replay.at(T), [replay, T]);
  const vp = fv.viewport ?? replay.viewports[0];
  const w = vp?.w ?? 1440;
  const h = vp?.h ?? 900;
  const current = useMemo(() => {
    let c: TimelineItem | null = null;
    for (const i of items) {
      if (i.t > T) break;
      if (i.kind !== "system" && i.kind !== "input") c = i;
    }
    return c;
  }, [items, T]);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Stage replay={replay} fv={fv} w={w} h={h} playing={playing} />
        <div className="shrink-0 border-t border-line bg-surface px-3 pb-2 pt-2">
          <div className="flex items-center gap-2">
            <button className="btn-ghost px-2" onClick={prev} aria-label="Previous action" title="Previous action">
              <SkipBack size={17} />
            </button>
            <button className="btn-primary px-3" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
              {playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <button className="btn-ghost px-2" onClick={next} aria-label="Next action" title="Next action">
              <SkipForward size={17} />
            </button>
            <span className="tnum w-28 shrink-0 text-xs text-muted">
              {fmtTime(T)} / {fmtTime(replay.duration)}
            </span>
            <Scrubber T={T} duration={duration} items={items} onSeek={seek} />
            <div className="flex shrink-0 items-center rounded-lg border border-line" role="group" aria-label="Speed">
              {SPEEDS.map((s) => (
                <button key={s} className={`px-1.5 py-1 text-xs ${speed === s ? "bg-sunken font-semibold" : "text-muted hover:text-ink"}`} onClick={() => setSpeed(s)}>
                  {s}×
                </button>
              ))}
            </div>
            <button className={`btn-ghost px-2 ${skipIdle ? "bg-sunken text-ink" : ""}`} onClick={() => setSkipIdle(!skipIdle)} title="Skip idle gaps longer than 3 s" aria-pressed={skipIdle}>
              <ChevronsRight size={16} /> <span className="hidden text-xs xl:inline">Skip idle</span>
            </button>
          </div>
          <div className="mt-0.5 truncate text-xs text-muted">{current ? `${fmtTime(current.t)}  ${current.text}` : "Start of recording"}</div>
        </div>
      </div>
      <aside className="flex h-[45vh] min-h-0 shrink-0 flex-col border-t border-line bg-surface lg:h-auto lg:w-[380px] lg:border-l lg:border-t-0">
        <div className="flex border-b border-line text-sm" role="tablist">
          {(["events", "metrics", "fidelity", "info"] as Tab[]).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`flex-1 px-2 py-2 capitalize ${tab === k ? "border-b-2 border-you font-medium" : "text-muted hover:text-ink"}`}>
              {k}
            </button>
          ))}
        </div>
        {tab === "events" && <EventsPanel items={items} T={T} onSeek={seek} />}
        {tab === "metrics" && <MetricsPanel rkey={rkey} />}
        {tab === "fidelity" && <FidelityPanel replay={replay} onSeek={seek} />}
        {tab === "info" && <InfoPanel replay={replay} rkey={rkey} meta={meta} />}
      </aside>
    </div>
  );
}
