/* Pure helpers (no DOM, no store) shared by the live telemetry and the replay
 * player, so both compute the identical checkpoint hash. */

/** JSON with sorted object keys (undefined / functions are skipped like JSON.stringify does). */
export function canonical(v: any): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "number") return Number.isFinite(v) ? JSON.stringify(v) : "null";
  if (typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map((x) => (x === undefined || typeof x === "function" ? "null" : canonical(x))).join(",") + "]";
  const keys = Object.keys(v).sort();
  const parts: string[] = [];
  for (const k of keys) {
    const x = v[k];
    if (x === undefined || typeof x === "function") continue;
    parts.push(JSON.stringify(k) + ":" + canonical(x));
  }
  return "{" + parts.join(",") + "}";
}

/** 32-bit FNV-1a of a string, as 8 hex digits. */
export function fnv1a(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** What a checkpoint hashes: the session state without the draft (edited locally)
 *  and the server clock (changes with every push). */
export function checkpointView(state: any): any {
  if (!state) return null;
  const { draft: _d, ...rest } = state;
  if (rest.negotiation && typeof rest.negotiation === "object") {
    const { server_time: _s, ...neg } = rest.negotiation;
    rest.negotiation = neg;
  }
  return rest;
}

export function stateHash(state: any): string {
  return fnv1a(canonical(checkpointView(state)));
}
