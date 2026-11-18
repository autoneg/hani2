import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Layer, lq } from "./layer";
import { toast } from "./toast";

export const getPath = (o: any, path: string) => path.split(".").reduce((x, k) => (x == null ? undefined : x[k]), o);
export const hasPath = (o: any, path: string) => {
  let x = o;
  for (const k of path.split(".")) {
    if (x == null || typeof x !== "object" || !(k in x)) return false;
    x = x[k];
  }
  return true;
};
export function setPath(o: any, path: string, v: any) {
  const keys = path.split(".");
  let x = o;
  keys.slice(0, -1).forEach((k) => (x = x[k] = x[k] && typeof x[k] === "object" ? x[k] : {}));
  x[keys[keys.length - 1]] = v;
}

/** A JSON settings file (env, llm, assistant, autopilot) as seen from one layer.
 *  Shows the values in effect at that layer; saving writes only the changed values to that layer's own file. */
export function useLayeredSettings(kind: string, layer: Layer) {
  const [own, setOwn] = useState<any>(null);
  const [eff, setEff] = useState<any>(null);
  const [edits, setEdits] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    return api(`/api/admin/settings/${kind}${lq(layer)}`)
      .then((d) => {
        if (d && "effective" in d && "own" in d) {
          setOwn(d.own ?? {});
          setEff(d.effective ?? {});
        } else {
          setOwn({});
          setEff(d ?? {});
        }
      })
      .catch((e) => setError(e.message));
  }, [kind, layer.id]);
  useEffect(() => {
    setEdits({});
    setEff(null);
    load();
  }, [load]);
  const get = (path: string) => (path in edits ? edits[path] : getPath(eff, path));
  const set = (path: string, v: any) => setEdits((e) => ({ ...e, [path]: v }));
  const overridden = (path: string) => layer.kind !== "settings" && own != null && hasPath(own, path);
  const save = async () => {
    const patch: any = {};
    Object.entries(edits).forEach(([p, v]) => setPath(patch, p, v));
    try {
      await api(`/api/admin/settings/${kind}${lq(layer)}`, { method: "PATCH", body: patch });
      setEdits({});
      await load();
      toast(`Saved to ${layer.label}. New sessions use it.`);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const reset = async (path: string) => {
    try {
      await api(`/api/admin/settings/${kind}${lq(layer)}&key=${encodeURIComponent(path)}`, { method: "DELETE" });
      setEdits(({ [path]: _, ...rest }) => rest);
      await load();
      toast("Back to the inherited value");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return { data: eff, own, get, set, save, reset, overridden, dirty: Object.keys(edits).length > 0, discard: () => setEdits({}), error, reload: load };
}
