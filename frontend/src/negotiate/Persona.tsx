import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { create } from "zustand";
import { Bot, X } from "lucide-react";
import { send, useStore } from "../store";
import type { SessionState } from "../types";
import type { Device } from "../device";
import { Assistant } from "./Assistant";

/** Whether the persona is on screen (the global toasts then leave the Assistant's notifications to it). */
export const usePersona = create<{ shown: boolean; setShown: (v: boolean) => void }>((set) => ({
  shown: false,
  setShown: (v) => set({ shown: v }),
}));

/** How the Assistant appears on this device: panel (opened from the header), persona or both.
 *  Phones always use the Assistant tab. */
export function assistantStyle(st: SessionState | null | undefined, device: Device): "panel" | "persona" | "both" {
  const s = st?.interface?.assistant?.style ?? "panel";
  return device === "phone" ? "panel" : s;
}

const SIZE = 56;
const GAP = 12;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** What the persona must not cover: the offer area and any control. */
const AVOID = "[data-persona-avoid], button, a[href], input, select, textarea, [role=tab]";

/** Keep the persona off the offer area and the controls of the page: it is moved straight up
 *  until it clears them (and stays where it was put if that would take it off the screen). */
function avoid(x: number, y: number): [number, number] {
  let top = y - SIZE / 2;
  const left = x - SIZE / 2;
  const els = [...document.querySelectorAll<HTMLElement>(AVOID)].filter((el) => !el.closest("[data-persona-ui]"));
  for (let i = 0; i < 8; i++) {
    let moved = false;
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      const overlaps = left < r.right && left + SIZE > r.left && top < r.bottom && top + SIZE > r.top;
      if (overlaps) {
        top = r.top - SIZE - GAP;
        moved = true;
      }
    });
    if (!moved) break;
  }
  if (top < 64) top = y - SIZE / 2;
  return [x, clamp(top + SIZE / 2, 64 + SIZE / 2, window.innerHeight - SIZE / 2 - 4)];
}

function useViewport() {
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const on = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}

/**
 * The Assistant as a character in a corner of the screen. Its notifications come out of it as
 * speech bubbles; clicking it opens the conversation next to it (or the side panel when the
 * Assistant also has the panel). The participant can drag it anywhere unless the admin fixed it;
 * where it was put is kept with the layout (`persona_x`, `persona_y`: its centre as fractions of
 * the window).
 */
export function Persona({ device, live = true }: { device: Device; live?: boolean }) {
  const st = useStore((s) => s.state);
  const open = useStore((s) => s.assistantOpen);
  const setOpen = useStore((s) => s.setAssistantOpen);
  const toasts = useStore((s) => s.toasts);
  const drop = useStore((s) => s.dropToast);
  const setShown = usePersona((s) => s.setShown);
  const vp = useViewport();
  const style = assistantStyle(st, device);
  const shown = !!st?.support && style !== "panel";
  useEffect(() => {
    setShown(shown);
    return () => setShown(false);
  }, [shown, setShown]);

  const sizes = st?.layout.sizes ?? {};
  const fx = typeof sizes.persona_x === "number" ? sizes.persona_x : null;
  const fy = typeof sizes.persona_y === "number" ? sizes.persona_y : null;
  const home: [number, number] = [fx !== null ? fx * vp.w : vp.w - SIZE / 2 - 20, fy !== null ? fy * vp.h : vp.h - SIZE / 2 - 20];
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const [pos, setPos] = useState<[number, number]>(home);
  const start = useRef<{ x: number; y: number; px: number; py: number; moved: boolean } | null>(null);
  const justDragged = useRef(false);

  // settle on the stored spot, clear of the offer controls (re-checked as the page changes)
  const phase = st?.phase;
  useLayoutEffect(() => {
    if (drag) return;
    setPos(avoid(clamp(home[0], SIZE / 2 + 4, vp.w - SIZE / 2 - 4), home[1]));
  }, [home[0], home[1], vp.w, vp.h, drag, phase, open]);

  if (!shown || !st?.support) return null;
  const sup = st.support;
  const movable = live && st.interface?.assistant?.movable !== false;
  const [x, y] = drag ?? pos;
  const right = x > vp.w / 2;
  const below = y < vp.h / 2;

  const onDown = (e: React.PointerEvent) => {
    if (!movable) return;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    start.current = { x: e.clientX, y: e.clientY, px: x, py: y, moved: false };
  };
  const onMove = (e: React.PointerEvent) => {
    const s = start.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    if (!s.moved && Math.hypot(dx, dy) < 5) return;
    s.moved = true;
    setDrag([clamp(s.px + dx, SIZE / 2, vp.w - SIZE / 2), clamp(s.py + dy, 64 + SIZE / 2, vp.h - SIZE / 2)]);
  };
  const onUp = () => {
    const s = start.current;
    start.current = null;
    if (!s?.moved || !drag) return;
    justDragged.current = true;
    const [nx, ny] = avoid(drag[0], drag[1]);
    setDrag(null);
    setPos([nx, ny]);
    const cur = useStore.getState().state;
    if (!cur) return;
    const next = { ...(cur.layout.sizes || {}), persona_x: Math.round(clamp(nx / vp.w, 0.05, 0.95) * 1000) / 1000, persona_y: Math.round(clamp(ny / vp.h, 0.05, 0.95) * 1000) / 1000 };
    useStore.setState((st2) => (st2.state ? { state: { ...st2.state, layout: { ...st2.state.layout, sizes: next } } } : {}));
    send({ type: "layout", sizes: next });
  };
  const click = () => {
    if (justDragged.current) {
      justDragged.current = false;
      return;
    }
    setOpen(!open);
  };

  // where the bubbles and the chat card go: towards the middle of the screen
  const anchor: React.CSSProperties = {
    position: "fixed",
    ...(right ? { right: vp.w - x - SIZE / 2 } : { left: x - SIZE / 2 }),
    ...(below ? { top: y + SIZE / 2 + 8 } : { bottom: vp.h - y + SIZE / 2 + 8 }),
  };
  const bubbles = toasts.filter((t) => t.source === "assistant").slice(-3);
  const chatHere = open && style === "persona";
  return (
    <>
      {!chatHere && bubbles.length > 0 && (
        <div data-persona-ui className={`pointer-events-none z-[45] flex w-[min(320px,calc(100vw-2rem))] gap-2 ${below ? "flex-col" : "flex-col-reverse"} ${right ? "items-end" : "items-start"}`} style={anchor} aria-live="polite">
          {bubbles.map((t) => (
            <div key={t.id} className={`enter pointer-events-auto relative flex items-start gap-2 rounded-2xl border border-you/25 bg-surface px-3 py-2 text-sm shadow-pop ${right ? "rounded-br-sm" : "rounded-bl-sm"}`} role="status">
              <button className="min-w-0 flex-1 text-left" onClick={() => { setOpen(true); drop(t.id); }} title="Open the conversation">
                {t.message}
              </button>
              <button className="text-muted hover:text-ink" onClick={() => drop(t.id)} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {chatHere && (
        <div data-persona-ui className="z-[46] flex h-[min(560px,calc(100vh-9rem))] w-[min(380px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line shadow-pop" style={anchor}>
          <Assistant fill />
        </div>
      )}
      <button
        className={`fixed z-[47] flex touch-none select-none items-center justify-center rounded-full shadow-pop transition-transform ${sup.enabled ? "bg-ink text-surface" : "bg-sunken text-muted"} ${movable ? "cursor-grab active:cursor-grabbing" : ""} ${open ? "ring-4 ring-you/30" : "hover:scale-105"}`}
        style={{ width: SIZE, height: SIZE, left: x - SIZE / 2, top: y - SIZE / 2 }}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={() => { start.current = null; setDrag(null); }}
        onClick={click}
        aria-label={`${sup.name}${movable ? " (drag to move)" : ""}`}
        aria-pressed={open}
        title={movable ? `${sup.name} — click to talk, drag to move` : sup.name}
        data-persona
        data-persona-ui
      >
        {sup.busy && <span className="absolute inset-0 animate-ping rounded-full bg-you/30" aria-hidden />}
        <Bot size={26} />
        <span className={`absolute right-0.5 top-0.5 h-3 w-3 rounded-full border-2 border-surface ${sup.enabled ? (sup.busy ? "bg-warn" : "bg-good") : "bg-muted"}`} />
      </button>
    </>
  );
}
