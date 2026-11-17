import { useEffect, useState } from "react";

/** Sub-path the server is mounted at behind a reverse proxy ("" at a site root). */
export const BASE: string = (
  document.querySelector('meta[name="hani2-base"]')?.getAttribute("content") || ""
).replace(/\/+$/, "");

/** Prefix an absolute in-app path ("/api/x", "/app") with the mount path. */
export function withBase(path: string): string {
  return BASE && path.startsWith("/") && !path.startsWith(BASE + "/") && path !== BASE ? BASE + path : path;
}

/** The in-app path of the current page (mount path removed). */
export function currentPath(): string {
  const p = location.pathname;
  if (BASE && (p === BASE || p.startsWith(BASE + "/"))) return p.slice(BASE.length) || "/";
  return p;
}

export function navigate(path: string, replace = false) {
  if (replace) history.replaceState(null, "", withBase(path));
  else history.pushState(null, "", withBase(path));
  window.dispatchEvent(new Event("hani-nav"));
}

export function usePath() {
  const [path, setPath] = useState(currentPath());
  useEffect(() => {
    const on = () => setPath(currentPath());
    window.addEventListener("popstate", on);
    window.addEventListener("hani-nav", on);
    return () => {
      window.removeEventListener("popstate", on);
      window.removeEventListener("hani-nav", on);
    };
  }, []);
  return path;
}

export function queryParams(): Record<string, string> {
  const out: Record<string, string> = {};
  new URLSearchParams(location.search).forEach((v, k) => (out[k] = v));
  return out;
}
