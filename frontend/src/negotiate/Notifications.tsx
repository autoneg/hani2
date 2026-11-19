import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, Bot, CheckCircle2, CircleAlert, Info, Pin as PinIcon, Trash2, TriangleAlert, X } from "lucide-react";
import { send, useStore } from "../store";
import type { NotificationItem, Pin } from "../types";
import { Markdown } from "../ui/Markdown";

// one shared empty list: a fresh [] per call makes zustand re-render forever (old recordings have no pins)
const NO_PINS: Pin[] = [];

const LEVEL = {
  info: { icon: Info, box: "border-you/30 bg-you/[0.06]", ic: "text-you" },
  success: { icon: CheckCircle2, box: "border-good/30 bg-good/[0.07]", ic: "text-good" },
  warning: { icon: TriangleAlert, box: "border-warn/40 bg-warn/[0.08]", ic: "text-warn" },
  error: { icon: CircleAlert, box: "border-bad/40 bg-bad/[0.07]", ic: "text-bad" },
};

/** Messages pinned at the top or bottom of the screen. They sit in the page flow,
 *  so the negotiation area shrinks to make room instead of being covered. */
export function PinnedMessages({ position, live = true }: { position: "top" | "bottom"; live?: boolean }) {
  const pins = useStore((s) => s.state?.pins ?? NO_PINS).filter((p: Pin) => p.position === position);
  if (!pins.length) return null;
  return (
    <div
      data-persona-avoid
      className={`scroll-thin flex max-h-[30vh] shrink-0 flex-col gap-1.5 overflow-y-auto bg-paper px-3 py-2 sm:px-4 ${position === "top" ? "border-b" : "border-t"} border-line`}
      role="region"
      aria-label={position === "top" ? "Pinned messages at the top" : "Pinned messages at the bottom"}
    >
      {pins.map((p) => {
        const L = LEVEL[p.level] ?? LEVEL.info;
        const I = L.icon;
        return (
          <div key={p.id} className={`enter flex items-start gap-2 rounded-lg border px-3 py-1.5 ${L.box}`} data-pin={p.id}>
            <span className={`mt-0.5 flex shrink-0 items-center gap-1 ${L.ic}`}>
              <PinIcon size={13} />
              <I size={15} />
            </span>
            <div className="min-w-0 flex-1">
              <Markdown text={p.text} size="sm" />
            </div>
            {p.dismissible && live && (
              <button className="text-muted hover:text-ink" onClick={() => send({ type: "unpin", id: p.id })} aria-label="Dismiss the pinned message">
                <X size={15} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

const SEEN_KEY = (sid: string) => `hani2-notifications-seen:${sid}`;

function readSeen(sid: string): number {
  try {
    return Number(localStorage.getItem(SEEN_KEY(sid)) || 0);
  } catch {
    return 0;
  }
}

function writeSeen(sid: string, id: number) {
  try {
    localStorage.setItem(SEEN_KEY(sid), String(id));
  } catch {
    /* ignore */
  }
}

const ago = (t: number) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

/** The bell in the header: every notification of this session, newest first. */
export function NotificationBell() {
  const st = useStore((s) => s.state);
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(0);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const sid = st?.sid ?? "";
  useEffect(() => setSeen(readSeen(sid)), [sid]);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!pop.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", h);
    window.addEventListener("keydown", k);
    return () => {
      document.removeEventListener("mousedown", h);
      window.removeEventListener("keydown", k);
    };
  }, [open]);
  const items: NotificationItem[] = st?.notifications ?? [];
  const last = items.length ? items[items.length - 1].id : 0;
  // a new session (or a restarted server) numbers its notifications from 1 again
  useEffect(() => {
    if (seen > last) {
      setSeen(0);
      writeSeen(sid, 0);
    }
  }, [seen, last, sid]);
  useEffect(() => {
    if (open && last > seen) {
      setSeen(last);
      writeSeen(sid, last);
    }
  }, [open, last, seen, sid]);
  if (!st || st.interface?.notification_center === false) return null;
  const unread = items.filter((n) => n.id > seen).length;
  const rect = btn.current?.getBoundingClientRect();
  return (
    <>
      <button ref={btn} className="btn-ghost relative px-2" onClick={() => setOpen(!open)} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} aria-expanded={open}>
        <Bell size={17} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-bad px-1 text-[10px] font-semibold leading-none text-white">{unread > 9 ? "9+" : unread}</span>
        )}
      </button>
      {open &&
        createPortal(
          <div
            ref={pop}
            className="enter fixed z-[60] flex max-h-[min(70vh,520px)] w-[min(380px,calc(100vw-1rem))] flex-col rounded-xl border border-line bg-surface shadow-pop"
            style={{ top: (rect?.bottom ?? 56) + 6, right: Math.max(8, window.innerWidth - (rect?.right ?? window.innerWidth - 8)) }}
            role="dialog"
            aria-label="Notifications"
          >
            <div className="flex items-center justify-between border-b border-line px-3 py-2">
              <div className="text-sm font-semibold">Notifications</div>
              {items.length > 0 && (
                <button className="btn-ghost px-1.5 py-0.5 text-xs" onClick={() => send({ type: "clear_notifications" })}>
                  <Trash2 size={13} /> Clear
                </button>
              )}
            </div>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="px-3 py-6 text-center text-sm text-muted">No notifications yet.</div>
              ) : (
                <ul className="divide-y divide-line/70">
                  {[...items].reverse().map((n) => {
                    const L = LEVEL[n.level] ?? LEVEL.info;
                    const I = n.source === "assistant" ? Bot : L.icon;
                    return (
                      <li key={n.id} className={`flex items-start gap-2.5 px-3 py-2 ${n.id > seen ? "bg-you/[0.04]" : ""}`}>
                        <I size={16} className={`mt-0.5 shrink-0 ${L.ic}`} />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm">{n.message}</div>
                          <div className="text-[11px] text-muted">
                            {n.source === "assistant" ? `${st.support?.name ?? "Assistant"} · ` : ""}
                            {ago(n.time)}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
