import { CheckCircle2, CircleAlert, Info, TriangleAlert, X } from "lucide-react";
import { useStore } from "../store";
import { usePersona } from "../negotiate/Persona";

const STYLE = {
  info: { icon: Info, cls: "border-you/25", ic: "text-you" },
  success: { icon: CheckCircle2, cls: "border-good/30", ic: "text-good" },
  warning: { icon: TriangleAlert, cls: "border-warn/40", ic: "text-warn" },
  error: { icon: CircleAlert, cls: "border-bad/40", ic: "text-bad" },
};

export function Toasts() {
  const all = useStore((s) => s.toasts);
  const persona = usePersona((s) => s.shown);
  const toasts = persona ? all.filter((t) => t.source !== "assistant") : all;
  const drop = useStore((s) => s.dropToast);
  const openAssistant = useStore((s) => s.setAssistantOpen);
  return (
    <div className="pointer-events-none fixed right-4 top-16 z-[70] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const st = STYLE[t.level] ?? STYLE.info;
        const I = st.icon;
        return (
          <div key={t.id} className={`enter pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-surface px-3 py-2.5 shadow-pop ${st.cls}`}>
            <I size={18} className={`mt-0.5 shrink-0 ${st.ic}`} />
            <div className="flex-1 text-sm">
              {t.message}
              {t.action?.kind === "open_assistant" && (
                <button className="mt-1 block text-sm font-medium text-you hover:underline" onClick={() => { openAssistant(true); drop(t.id); }}>
                  {t.action.label}
                </button>
              )}
            </div>
            <button className="text-muted hover:text-ink" onClick={() => drop(t.id)} aria-label="Dismiss">
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
