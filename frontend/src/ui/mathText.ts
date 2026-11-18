/**
 * Find TeX math in Markdown text, without touching code.
 *
 * The rule (Pandoc's; the docs' arithmatex "smart dollar" is the same without
 * the digit check):
 *  - `$$ … $$` is display math (it may span lines but not a blank line);
 *  - `$ … $` is inline math only when the opening `$` is followed by a
 *    non-space character and the closing `$` is preceded by a non-space
 *    character and not followed by a digit; the math holds no other `$`;
 *  - `\$` is a literal dollar sign; code spans and fenced code blocks are left alone.
 * So "a $5 price", "between $5 and $10" and "$5-$10" stay text.
 *
 * Pure (no imports) so that it can be tested with `node --test`.
 */

export type MathPart = { kind: "text"; text: string } | { kind: "math"; tex: string; display: boolean };

/** Markers of the inline-code placeholders `protectMath` writes. */
export const INLINE_MARK = "⁣m:";
export const DISPLAY_MARK = "⁣d:";

const isSpace = (c: string | undefined) => c === undefined || /\s/.test(c);
const isDigit = (c: string | undefined) => c !== undefined && c >= "0" && c <= "9";

/** Split a piece of text (no fenced code) into text, code spans and math. */
export function splitMath(text: string): MathPart[] {
  const out: MathPart[] = [];
  let buf = "";
  const push = (p: MathPart) => {
    if (buf) out.push({ kind: "text", text: buf });
    buf = "";
    out.push(p);
  };
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === "\\" && i + 1 < n) {
      buf += c + text[i + 1];
      i += 2;
      continue;
    }
    if (c === "`") {
      let j = i;
      while (j < n && text[j] === "`") j++;
      const run = text.slice(i, j);
      // a code span ends at the next run of exactly the same length
      let k = j;
      let end = -1;
      while (k < n) {
        const s = text.indexOf(run, k);
        if (s < 0) break;
        let e = s + run.length;
        if (text[s - 1] !== "`" && text[e] !== "`") {
          end = e;
          break;
        }
        while (e < n && text[e] === "`") e++;
        k = e;
      }
      if (end < 0) {
        buf += run;
        i = j;
      } else {
        buf += text.slice(i, end);
        i = end;
      }
      continue;
    }
    if (c === "$" && text[i + 1] === "$") {
      const close = findClose(text, i + 2, "$$");
      if (close >= 0) {
        const tex = text.slice(i + 2, close).trim();
        if (tex) {
          push({ kind: "math", tex, display: true });
          i = close + 2;
          continue;
        }
      }
      buf += "$$";
      i += 2;
      continue;
    }
    if (c === "$" && !isSpace(text[i + 1])) {
      const close = findClose(text, i + 1, "$");
      if (close > i + 1 && !isSpace(text[close - 1]) && !isDigit(text[close + 1])) {
        push({ kind: "math", tex: text.slice(i + 1, close), display: false });
        i = close + 1;
        continue;
      }
    }
    buf += c;
    i++;
  }
  if (buf) out.push({ kind: "text", text: buf });
  return out;
}

/** The index of the first unescaped `delim` at or after `from`, or -1 (also at a blank line). */
function findClose(text: string, from: number, delim: "$" | "$$"): number {
  for (let j = from; j < text.length; j++) {
    const c = text[j];
    if (c === "\\") {
      j++;
      continue;
    }
    if (c === "\n" && /^\n[ \t]*\n/.test(text.slice(j))) return -1;
    if (c === "$") {
      if (delim === "$") return text[j + 1] === "$" ? -1 : j;
      if (text[j + 1] === "$") return j;
    }
  }
  return -1;
}

/**
 * Replace the math of a Markdown text by inline-code placeholders
 * (`INLINE_MARK` / `DISPLAY_MARK` + the URI-encoded TeX) that a Markdown
 * renderer's `code` component turns into KaTeX. Fenced code blocks are kept.
 */
export function protectMath(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let block: string[] = [];
  let fence: string | null = null;
  const flush = () => {
    if (!block.length) return;
    out.push(
      splitMath(block.join("\n"))
        .map((p) => (p.kind === "text" ? p.text : "`" + (p.display ? DISPLAY_MARK : INLINE_MARK) + encodeURIComponent(p.tex) + "`"))
        .join(""),
    );
    block = [];
  };
  for (const line of lines) {
    const m = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (fence) {
      out.push(line);
      if (m && m[1][0] === fence[0] && m[1].length >= fence.length && !line.trim().slice(m[1].length).trim()) fence = null;
    } else if (m) {
      flush();
      fence = m[1];
      out.push(line);
    } else block.push(line);
  }
  flush();
  return out.join("\n");
}

/** The TeX of a placeholder written by `protectMath` (or null). */
export function placeholderTex(code: string): { tex: string; display: boolean } | null {
  for (const [mark, display] of [
    [INLINE_MARK, false],
    [DISPLAY_MARK, true],
  ] as const)
    if (code.startsWith(mark)) {
      try {
        return { tex: decodeURIComponent(code.slice(mark.length)), display };
      } catch {
        return null;
      }
    }
  return null;
}
