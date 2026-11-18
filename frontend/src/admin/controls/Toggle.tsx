/** A macOS-style switch (role="switch"). */
export function Toggle({ value, onChange, label, disabled }: { value: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!value}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!value)}
      className={`relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full transition-colors disabled:opacity-45 ${value ? "bg-you" : "bg-line"}`}
    >
      <span className={`absolute h-[18px] w-[18px] rounded-full bg-white shadow-[0_1px_3px_rgb(0_0_0/0.3)] transition-transform ${value ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
    </button>
  );
}
