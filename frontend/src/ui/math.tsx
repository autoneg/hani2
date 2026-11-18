import { useEffect, useState } from "react";

/** KaTeX, loaded on first use (its own chunk with its CSS and fonts). */
type Katex = typeof import("katex").default;
let katex: Katex | null = null;
let loading: Promise<Katex> | null = null;

export function loadKatex(): Promise<Katex> {
  if (!loading)
    loading = Promise.all([import("katex"), import("katex/dist/katex.min.css")]).then(([k]) => {
      katex = k.default;
      return katex;
    });
  return loading;
}

export function useKatex(): Katex | null {
  const [k, setK] = useState<Katex | null>(katex);
  useEffect(() => {
    if (!k) loadKatex().then(setK).catch(() => {});
  }, [k]);
  return k;
}

/** TeX as HTML. KaTeX escapes its input and, without `trust`, allows no links or raw HTML. */
export function texToHtml(k: Katex, tex: string, display: boolean): string {
  return k.renderToString(tex, { displayMode: display, throwOnError: false, output: "htmlAndMathml", strict: "ignore" });
}

/** One formula; shows the TeX source until KaTeX has loaded. */
export function Tex({ tex, display = false, className = "" }: { tex: string; display?: boolean; className?: string }) {
  const k = useKatex();
  if (!k)
    return <code className={`${display ? "md-math-display py-2" : ""} text-muted ${className}`}>{tex}</code>;
  // a span (styled as a block for display math) so that it may sit inside a paragraph
  return <span className={`${display ? "md-math-display" : "md-math"} ${className}`} dangerouslySetInnerHTML={{ __html: texToHtml(k, tex, display) }} />;
}
