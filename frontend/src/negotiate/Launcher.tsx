import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, LayoutGrid } from "lucide-react";
import { useStore } from "../store";
import type { ToolInfo } from "../types";
import { Icon } from "../ui/Icon";
import { POPUP_KEY, closePopup, openPopup } from "./ToolPane";

/** The tools the launcher offers: the offer generators first (by order), then the others. */
export function useLaunchable(): { generators: ToolInfo[]; others: ToolInfo[] } {
  const tools = useStore((s) => s.state?.tools ?? []);
  const byOrder = (a: ToolInfo, b: ToolInfo) => a.order - b.order || a.name.localeCompare(b.name);
  const panes = ["upper", "lower", "side"];
  return {
    generators: tools.filter((t) => t.generator).sort(byOrder),
    others: tools.filter((t) => !t.generator).sort((a, b) => panes.indexOf(a.pane) - panes.indexOf(b.pane) || byOrder(a, b)),
  };
}

function toggle(t: ToolInfo, from: string) {
  if (useStore.getState().ui[POPUP_KEY] === t.id) closePopup();
  else openPopup(t, from);
}

/** One click to the first offer generator (by order, so a study that drops one still gets
 *  the next), opened in a popup next to the offer. Pressed while it is open; a second click
 *  closes it. */
export function GeneratorButton({ onOpen }: { onOpen?: () => void }) {
  const { generators } = useLaunchable();
  const open = useStore((s) => s.ui[POPUP_KEY] as string | undefined);
  const g = generators[0];
  if (!g) return null;
  const on = open === g.id;
  return (
    <button
      className={`btn px-3 py-2 ${on ? "border border-you bg-you/10 text-you" : "border border-line bg-surface hover:border-you/50"}`}
      aria-pressed={on}
      data-testid="launch-generator"
      title={`${g.description || g.name} Opens in a popup next to your offer.`}
      onClick={() => {
        if (!on) onOpen?.();
        toggle(g, "dock");
      }}
    >
      <Icon name={g.icon} size={15} /> {g.name}
    </button>
  );
}

/** A menu of every tool (offer generators first) that opens the chosen one in a popup:
 *  the way to the tools in views that do not show them all (simple, focus, tablets, phones). */
export function ToolsMenu({ onOpenGenerator }: { onOpenGenerator?: () => void }) {
  const { generators, others } = useLaunchable();
  const current = useStore((s) => s.ui[POPUP_KEY] as string | undefined);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  // the menu is portalled (the action panel scrolls and would clip it) and placed by the button:
  // above it when there is room (the panel sits at the bottom of the page), else below
  const [place, setPlace] = useState<React.CSSProperties>({});
  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const at = () => {
      const r = btn.current!.getBoundingClientRect();
      const left = Math.max(8, Math.min(window.innerWidth - 296, r.left));
      setPlace(r.top > 320 || r.top > window.innerHeight - r.bottom ? { left, bottom: window.innerHeight - r.top + 4 } : { left, top: r.bottom + 4 });
    };
    at();
    window.addEventListener("resize", at);
    return () => window.removeEventListener("resize", at);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const out = (e: MouseEvent) =>
      !ref.current?.contains(e.target as Node) && !menu.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", out);
    document.addEventListener("keydown", esc);
    first.current?.focus();
    return () => {
      document.removeEventListener("mousedown", out);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  if (!generators.length && !others.length) return null;
  const item = (t: ToolInfo, i: number, isGen: boolean) => {
    const on = current === t.id;
    return (
      <button
        key={t.id}
        ref={i === 0 ? first : undefined}
        role="menuitem"
        aria-current={on || undefined}
        className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-sunken focus-visible:bg-sunken ${on ? "bg-you/10" : ""}`}
        onClick={() => {
          setOpen(false);
          if (!on && isGen) onOpenGenerator?.();
          toggle(t, "menu");
        }}
      >
        <Icon name={t.icon} size={16} className="mt-0.5 shrink-0 text-muted" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-medium">
            {t.name}
            {on && <span className="rounded bg-you/15 px-1 text-[10px] font-medium text-you">open</span>}
          </span>
          {t.description && <span className="line-clamp-2 block text-[11px] leading-snug text-muted">{t.description}</span>}
        </span>
      </button>
    );
  };
  return (
    <div className="relative" ref={ref}>
      <button
        ref={btn}
        className="btn border border-line bg-surface px-3 py-2 hover:border-you/50"
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid="launch-tools"
        title="Open any tool in a popup"
        onClick={() => setOpen(!open)}
      >
        <LayoutGrid size={15} /> Tools <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && createPortal(
        <div
          ref={menu}
          role="menu"
          aria-label="Open a tool"
          style={place}
          className="enter scroll-thin fixed z-[56] max-h-[min(60vh,28rem)] w-72 overflow-y-auto rounded-xl border border-line bg-surface p-1 shadow-pop"
        >
          {generators.length > 0 && (
            <>
              <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Offer generators</div>
              {generators.map((t, i) => item(t, i, true))}
            </>
          )}
          {others.length > 0 && (
            <>
              <div className={`px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted ${generators.length ? "mt-1 border-t border-line" : ""}`}>Other tools</div>
              {others.map((t, i) => item(t, generators.length + i, false))}
            </>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}
