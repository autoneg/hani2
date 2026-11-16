import { useEffect, useRef, useState } from "react";

let plotlyPromise: Promise<any> | null = null;
const loadPlotly = () => (plotlyPromise ??= import("plotly.js-dist-min").then((m: any) => m.default ?? m));

function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  const rgb = (v: string) => `rgb(${cs.getPropertyValue(v).trim().split(" ").join(",")})`;
  return { ink: rgb("--ink"), muted: rgb("--muted"), line: rgb("--line") };
}

export function Plot({ figure, height }: { figure: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dark, setDark] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setDark((d) => d + 1);
    mq.addEventListener("change", on);
    const obs = new MutationObserver(on);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      mq.removeEventListener("change", on);
      obs.disconnect();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadPlotly()
      .then((Plotly) => {
        if (cancelled || !ref.current) return;
        const c = themeColors();
        const layout = {
          ...(figure.layout || {}),
          height: height ?? figure.layout?.height ?? 260,
          autosize: true,
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { family: '"Instrument Sans Variable", system-ui, sans-serif', color: c.ink, size: 12 },
          xaxis: { gridcolor: c.line, zerolinecolor: c.line, linecolor: c.line, ...(figure.layout?.xaxis || {}) },
          yaxis: { gridcolor: c.line, zerolinecolor: c.line, linecolor: c.line, ...(figure.layout?.yaxis || {}) },
        };
        delete (layout as any).template;
        Plotly.react(ref.current, figure.data || [], layout, { displayModeBar: false, responsive: true });
      })
      .catch((e) => setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [figure, height, dark]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => loadPlotly().then((P) => el.isConnected && P.Plots.resize(el)));
    ro.observe(el);
    return () => {
      ro.disconnect();
      loadPlotly().then((P) => P.purge(el));
    };
  }, []);

  if (error) return <div className="text-sm text-bad">Could not draw the chart: {error}</div>;
  return <div ref={ref} className="w-full" style={{ minHeight: height ?? figure.layout?.height ?? 260 }} />;
}
