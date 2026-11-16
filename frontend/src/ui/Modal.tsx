import { useEffect } from "react";
import { X } from "lucide-react";

export function Modal({ open, onClose, title, children, wide = false }: { open: boolean; onClose?: () => void; title?: React.ReactNode; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open || !onClose) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[rgb(10_14_22/0.5)] p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div role="dialog" aria-modal className={`enter max-h-[90vh] w-full overflow-auto rounded-xl border border-line bg-surface shadow-pop ${wide ? "max-w-2xl" : "max-w-md"}`}>
        {(title || onClose) && (
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="font-semibold">{title}</div>
            {onClose && (
              <button className="btn-ghost px-1.5" onClick={onClose} aria-label="Close">
                <X size={16} />
              </button>
            )}
          </div>
        )}
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
