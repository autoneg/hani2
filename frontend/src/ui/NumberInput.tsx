import { useEffect, useState } from "react";

/** Parses ``text`` as a number in [min, max] (a whole one when ``int``); ``null`` if it is not one. */
export function parseNumber(text: string, min?: number | null, max?: number | null, int?: boolean): number | null {
  const t = text.trim();
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n) || (int && !Number.isInteger(n))) return null;
  if ((min != null && n < min) || (max != null && n > max)) return null;
  return n;
}

/** A number field that keeps what is typed locally and only commits valid, in-range numbers.
 *  Partial or out-of-range text is flagged and reverts to the committed value on blur. */
export function NumberInput({ value, onCommit, min, max, int, step, className = "field tnum", ...rest }: {
  value: number | null | undefined;
  onCommit: (v: number) => void;
  min?: number | null;
  max?: number | null;
  int?: boolean;
  step?: number | string | null;
  className?: string;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  const shown = value == null ? "" : String(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText((t) => (parseNumber(t, min, max, int) === value ? t : shown)), [value]);
  const invalid = text.trim() !== "" && parseNumber(text, min, max, int) === null;
  return (
    <input
      {...rest}
      type="number"
      className={`${className} ${invalid ? "border-bad focus:border-bad" : ""}`}
      min={min ?? undefined}
      max={max ?? undefined}
      step={step ?? (int ? 1 : "any")}
      value={text}
      aria-invalid={invalid || undefined}
      title={invalid ? `Enter a number${min != null && max != null ? ` from ${min} to ${max}` : ""}` : undefined}
      onChange={(e) => {
        setText(e.target.value);
        const n = parseNumber(e.target.value, min, max, int);
        if (n !== null && n !== value) onCommit(n);
      }}
      onBlur={() => setText(shown)}
    />
  );
}
