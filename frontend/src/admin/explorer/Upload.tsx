import { useRef, useState } from "react";
import { Loader2, Upload as UploadIcon } from "lucide-react";
import { toast } from "../toast";

/** Choose or drop a file; ``send`` uploads it (errors become a toast). */
export function Upload({ accept, send, label = "Choose file…", disabled }: { accept: string; send: (f: File) => Promise<void>; label?: string; disabled?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const go = async (f: File) => {
    setBusy(true);
    try {
      await send(f);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  };
  return (
    <div
      onDragOver={(e) => (e.preventDefault(), setOver(true))}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !disabled) go(f);
      }}
      className={`flex items-center gap-2 rounded-lg border border-dashed px-2 py-1 ${over ? "border-you bg-you/5" : "border-line"} ${disabled ? "opacity-60" : ""}`}
    >
      <span className="hidden text-xs text-muted sm:inline">Drop here or</span>
      <input ref={ref} type="file" accept={accept} className="sr-only" aria-label={label} onChange={(e) => e.target.files?.[0] && go(e.target.files[0])} disabled={disabled || busy} />
      <button type="button" className="btn-secondary py-1 text-xs" disabled={disabled || busy} onClick={() => ref.current?.click()}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <UploadIcon size={13} />} {label}
      </button>
    </div>
  );
}
