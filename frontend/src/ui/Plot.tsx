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

  // Draw when the browser is idle and the chart is on screen, so a burst of
  // tool updates never blocks typing or clicking. Only the latest figure is drawn.
  const visible = useRef(true);
  const pending = useRef<(() => void) | null>(null);
  useEffect(() => {
    let cancelled = false;
    const draw = () =>
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
          return Plotly.react(ref.current, figure.data || [], layout, { displayModeBar: false, responsive: false });
        })
        .catch((e) => setError(String(e)));
    const schedule = () => {
      pending.current = null;
      const ric = (window as any).requestIdleCallback as undefined | ((cb: () => void, o?: any) => number);
      const handle = ric ? ric(() => !cancelled && draw(), { timeout: 250 }) : window.setTimeout(() => !cancelled && draw(), 16);
      return () => ((window as any).cancelIdleCallback && ric ? (window as any).cancelIdleCallback(handle) : window.clearTimeout(handle));
    };
    let cancel: (() => void) | undefined;
    if (visible.current) cancel = schedule();
    else pending.current = () => (cancel = schedule());
    return () => {
      cancelled = true;
      cancel?.();
      pending.current = null;
    };
  }, [figure, height, dark]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // charts in hidden tabs or scrolled away wait until they are seen
    const io = new IntersectionObserver((entries) => {
      const on = entries.some((e) => e.isIntersecting);
      visible.current = on;
      if (on && pending.current) pending.current();
    });
    io.observe(el);
    // resize at most once per frame, and once more when resizing settles
    let frame = 0;
    let settle = 0;
    const resize = () => loadPlotly().then((P) => el.isConnected && (el as any)._fullLayout && P.Plots.resize(el));
    const ro = new ResizeObserver(() => {
      // while a divider is being dragged, only resize once the drag settles
      const dragging = document.body.classList.contains("resizing-col") || document.body.classList.contains("resizing-row");
      if (!frame && !dragging) frame = requestAnimationFrame(() => ((frame = 0), resize()));
      window.clearTimeout(settle);
      settle = window.setTimeout(resize, 150);
    });
    ro.observe(el);
    return () => {
      io.disconnect();
      ro.disconnect();
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      loadPlotly().then((P) => P.purge(el));
    };
  }, []);

  if (error) return <div className="text-sm text-bad">Could not draw the chart: {error}</div>;
  return <div ref={ref} className="w-full" style={{ minHeight: height ?? figure.layout?.height ?? 260 }} />;
}
