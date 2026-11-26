import { useEffect, useState } from "react";
import { useStore } from "../store";

/** Controls the participant must always be able to see and use. A custom style
 *  sheet that hides one of them (directly or through an ancestor) is dropped. */
const ESSENTIAL = ["accept", "end", "reject", "offer"];

function hidden(el: Element): boolean {
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return true;
  let opacity = 1;
  for (let e: Element | null = el; e; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.visibility === "hidden" || cs.visibility === "collapse") return true;
    opacity *= parseFloat(cs.opacity || "1");
    if (opacity < 0.3) return true;
  }
  // pushed entirely off the page sideways or upwards (scrolling down inside the dock is fine)
  return r.right < 0 || r.left > window.innerWidth || r.bottom < 0;
}

function brokenControls(): string[] {
  const out: string[] = [];
  for (const id of ESSENTIAL) {
    for (const el of Array.from(document.querySelectorAll(`[data-anchor="${id}"]`))) {
      if (hidden(el)) out.push(id);
    }
  }
  return out;
}

/** The style sheet the Assistant added to the page (state.custom_css). The
 *  server already rejected url(), @import and !important; here the sheet is
 *  dropped again if it hides the accept, end, counter-offer or send controls. */
export function CustomStyle() {
  const css = useStore((s) => s.state?.custom_css) || "";
  const phase = useStore((s) => s.state?.phase);
  const turns = useStore((s) => s.state?.history.length ?? 0);
  const [rejected, setRejected] = useState<string | null>(null);
  const active = css && css !== rejected ? css : "";

  useEffect(() => {
    if (!active) return;
    // compare with the page without the sheet: only controls the sheet hides count
    const el = document.getElementById("hani2-custom-css") as HTMLStyleElement | null;
    const id = requestAnimationFrame(() => {
      if (!el) return;
      const withSheet = brokenControls();
      if (!withSheet.length) return;
      el.disabled = true;
      const without = new Set(brokenControls());
      el.disabled = false;
      const caused = withSheet.filter((x) => !without.has(x));
      if (caused.length) {
        setRejected(active);
        useStore.getState().send({ type: "event", name: "custom_css_rejected", component: "custom_css", value: { hides: caused } });
      }
    });
    return () => cancelAnimationFrame(id);
  }, [active, phase, turns]);

  if (!active) return null;
  return <style id="hani2-custom-css">{active}</style>;
}
