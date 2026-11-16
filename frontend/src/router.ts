import { useEffect, useState } from "react";

export function navigate(path: string, replace = false) {
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  window.dispatchEvent(new Event("hani-nav"));
}

export function usePath() {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const on = () => setPath(location.pathname);
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
