import { useEffect, useRef, useState, type RefObject } from "react";
import { send, useStore } from "../store";

/** A size the participant can change by dragging a divider. The value is a
 *  fraction of the container (0–1). It is stored in the session layout
 *  (`layout.sizes[key]`) so it survives reloads and the Assistant can set it;
 *  `undefined` means "use the default". */
export function useLayoutSize(key: string): [number | undefined, (v: number | undefined) => void, (v: number | undefined) => void] {
  const stored = useStore((s) => s.state?.layout.sizes?.[key]) as number | undefined;
  const [live, setLive] = useState<number | undefined>(stored);
  const dragging = useRef(false);
  useEffect(() => {
    if (!dragging.current) setLive(stored);
  }, [stored]);
  const change = (v: number | undefined) => {
    dragging.current = true;
    setLive(v);
  };
  const commit = (v: number | undefined) => {
    dragging.current = false;
    setLive(v);
    const st = useStore.getState().state;
    if (!st) return;
    const sizes: Record<string, number> = { ...(st.layout.sizes || {}) };
    if (v === undefined) delete sizes[key];
    else sizes[key] = Math.round(v * 1000) / 1000;
    useStore.setState((s) => (s.state ? { state: { ...s.state, layout: { ...s.state.layout, sizes } } } : {}));
    send({ type: "layout", sizes });
  };
  return [live, change, commit];
}

/**
 * A draggable divider. `dir="col"` sits between two columns (drag left/right),
 * `dir="row"` between two rows (drag up/down). The sized pane is the one
 * before the divider, or the one after it when `after` is set. Arrow keys
 * nudge it, Home/double-click restores the default.
 */
export function Splitter({
  dir,
  container,
  value,
  fallback,
  onChange,
  onCommit,
  after = false,
  min = 0.15,
  max = 0.8,
  label,
}: {
  dir: "col" | "row";
  container: RefObject<HTMLElement | null>;
  value: number | undefined;
  /** measures the pane's current share when no size is stored yet */
  fallback: () => number;
  onChange: (v: number) => void;
  onCommit: (v: number | undefined) => void;
  after?: boolean;
  min?: number;
  max?: number;
  label: string;
}) {
  const [active, setActive] = useState(false);
  const last = useRef<number | undefined>(value);
  const clamp = (v: number) => Math.max(min, Math.min(max, v));
  const at = (e: PointerEvent | React.PointerEvent) => {
    const el = container.current;
    if (!el) return undefined;
    const r = el.getBoundingClientRect();
    const f = dir === "col" ? (e.clientX - r.left) / r.width : (e.clientY - r.top) / r.height;
    return clamp(after ? 1 - f : f);
  };
  const down = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    last.current = undefined; // a plain click (no move) must not re-commit an old size
    setActive(true);
    document.body.classList.add(dir === "col" ? "resizing-col" : "resizing-row");
  };
  const move = (e: React.PointerEvent) => {
    if (!active) return;
    const v = at(e);
    if (v !== undefined) {
      last.current = v;
      onChange(v);
    }
  };
  const up = (e: React.PointerEvent) => {
    if (!active) return;
    setActive(false);
    document.body.classList.remove("resizing-col", "resizing-row");
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
    if (last.current !== undefined) onCommit(last.current);
  };
  const key = (e: React.KeyboardEvent) => {
    const grow = dir === "col" ? (after ? "ArrowLeft" : "ArrowRight") : after ? "ArrowUp" : "ArrowDown";
    const shrink = dir === "col" ? (after ? "ArrowRight" : "ArrowLeft") : after ? "ArrowDown" : "ArrowUp";
    const cur = value ?? fallback();
    let v: number | undefined;
    if (e.key === grow) v = clamp(cur + 0.02);
    else if (e.key === shrink) v = clamp(cur - 0.02);
    else if (e.key === "Home") v = undefined;
    else return;
    e.preventDefault();
    last.current = v;
    onCommit(v);
  };
  const col = dir === "col";
  return (
    <div
      role="separator"
      aria-orientation={col ? "vertical" : "horizontal"}
      aria-label={label}
      aria-valuemin={Math.round(min * 100)}
      aria-valuemax={Math.round(max * 100)}
      aria-valuenow={Math.round((value ?? fallback()) * 100)}
      title={`${label} — drag to resize, double-click to reset`}
      tabIndex={0}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onDoubleClick={() => onCommit(undefined)}
      onKeyDown={key}
      className={`group relative z-10 shrink-0 touch-none select-none outline-none ${col ? "-mx-1 w-2 cursor-col-resize" : "-my-1 h-2 cursor-row-resize"}`}
    >
      <div
        className={`pointer-events-none absolute transition-colors ${
          col ? "inset-y-0 left-1/2 w-px -translate-x-1/2" : "inset-x-0 top-1/2 h-px -translate-y-1/2"
        } ${active ? "bg-you" : "bg-line group-hover:bg-you/60 group-focus-visible:bg-you"}`}
      />
      <div
        className={`pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full transition-opacity ${
          col ? "h-8 w-1" : "h-1 w-8"
        } ${active ? "bg-you opacity-100" : "bg-muted/50 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"}`}
      />
    </div>
  );
}
