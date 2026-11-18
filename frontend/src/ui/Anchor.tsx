import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useStore, send } from "../store";

const NOTE: Record<string, string> = {
  info: "border-you/30 bg-you/10 text-ink",
  success: "border-good/30 bg-good/10 text-ink",
  tip: "border-good/30 bg-good/10 text-ink",
  warning: "border-bad/30 bg-bad/10 text-ink",
};

/** Wraps an element the Assistant (or a tool) can highlight or annotate. */
export function Anchor({
  id,
  children,
  className = "",
  as: Tag = "div",
  notePlacement = "below",
}: {
  id: string;
  children: React.ReactNode;
  className?: string;
  as?: any;
  notePlacement?: "below" | "above";
}) {
  const hl = useStore((s) => s.state?.highlights.find((h) => h.target.toLowerCase() === id.toLowerCase()));
  const note = useStore((s) => {
    const a = s.state?.annotations || {};
    const k = Object.keys(a).find((x) => x.toLowerCase() === id.toLowerCase());
    return k ? a[k] : undefined;
  });
  const [expired, setExpired] = useState<string | null>(null);
  useEffect(() => {
    if (!hl?.duration) return;
    const t = window.setTimeout(() => setExpired(hl.id), hl.duration * 1000);
    return () => window.clearTimeout(t);
  }, [hl?.id, hl?.duration]);
  const active = hl && expired !== hl.id;
  const cls = active ? (hl!.style === "glow" ? "hl-glow" : hl!.style === "spotlight" ? "hl-spotlight" : "hl-pulse") : "";
  const noteEl = note && (
    <div role="note" className={`enter mt-1.5 rounded-md border px-2 py-1 text-xs ${NOTE[note.kind] ?? NOTE.info}`}>
      {note.text}
    </div>
  );
  return (
    <Tag data-anchor={id} className={`${className} ${cls} ${active && hl!.message ? "relative" : ""}`}>
      {notePlacement === "above" && noteEl}
      {children}
      {active && hl!.message && (
        <div role="status" className="enter pointer-events-none absolute left-0 top-full z-50 mt-2 flex w-max max-w-[18rem] items-start gap-2 rounded-lg bg-you px-3 py-2 text-sm text-white shadow-pop">
          <span className="absolute -top-1 left-4 h-2 w-2 rotate-45 bg-you" aria-hidden />
          <span className="flex-1">{hl!.message}</span>
          <button className="pointer-events-auto opacity-80 hover:opacity-100" aria-label="Dismiss" onClick={() => send({ type: "clear_highlight", target: hl!.target })}>
            <X size={14} />
          </button>
        </div>
      )}
      {notePlacement === "below" && noteEl}
    </Tag>
  );
}
