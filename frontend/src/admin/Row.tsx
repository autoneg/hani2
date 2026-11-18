import { RotateCcw } from "lucide-react";

/** One row of a group: label and hint on the left, the control on the right.
 *  ``wide`` puts the control under the label (text areas, long lists).
 *  ``overridden`` marks a value set in the chosen layer, with a reset button. */
export function Row({ id, label, hint, children, wide, icon, overridden, onReset }: {
  id?: string; label: React.ReactNode; hint?: React.ReactNode; children?: React.ReactNode; wide?: boolean; icon?: React.ReactNode; overridden?: boolean; onReset?: () => void;
}) {
  return (
    <div id={id ? `setting-${id}` : undefined} data-setting={id} className={`scroll-mt-24 px-4 py-2.5 ${wide ? "" : "flex flex-wrap items-center gap-x-6 gap-y-2 sm:flex-nowrap"}`}>
      <div className={`flex min-w-0 items-start gap-3 ${wide ? "mb-2" : "min-w-[min(100%,11rem)] flex-1"}`}>
        {icon && <div className="mt-0.5 shrink-0">{icon}</div>}
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm text-ink">
            <span>{label}</span>
            {overridden && (
              <span className="inline-flex items-center gap-1 rounded bg-you/10 px-1.5 text-[0.68rem] font-medium text-you" title="Set in this layer">
                set here
                {onReset && (
                  <button type="button" className="hover:text-ink" aria-label="Use the inherited value" title="Use the inherited value" onClick={onReset}>
                    <RotateCcw size={11} />
                  </button>
                )}
              </span>
            )}
          </div>
          {hint && <div className="text-xs leading-snug text-muted">{hint}</div>}
        </div>
      </div>
      {children !== undefined && <div className={wide ? "min-w-0" : "ml-auto flex min-w-0 max-w-full shrink-0 items-center justify-end gap-2 sm:max-w-[60%]"}>{children}</div>}
    </div>
  );
}

/** A read-only row (label and value). */
export function InfoRow({ id, label, value, hint, mono }: { id?: string; label: React.ReactNode; value: React.ReactNode; hint?: React.ReactNode; mono?: boolean }) {
  return (
    <Row id={id} label={label} hint={hint}>
      <span className={`min-w-0 break-all text-right text-sm text-muted ${mono ? "font-mono text-xs" : ""}`}>{value}</span>
    </Row>
  );
}

/** A small coloured icon tile, as in the sidebar. */
export function Tile({ icon: I, color = "bg-you", size = 15 }: { icon: any; color?: string; size?: number }) {
  return (
    <span className={`inline-flex h-[22px] w-[22px] items-center justify-center rounded-[6px] text-white ${color}`}>
      <I size={size - 2} strokeWidth={2.2} />
    </span>
  );
}
