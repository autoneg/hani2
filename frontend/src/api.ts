import { withBase } from "./router";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const res = await fetch(withBase(path), {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

/** POST raw bytes (e.g. a file) and read the JSON answer. */
export async function apiRaw<T = any>(path: string, body: Blob | ArrayBuffer): Promise<T> {
  const res = await fetch(withBase(path), { method: "POST", body, credentials: "same-origin", headers: { "Content-Type": "application/octet-stream" } });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

/** POST a multipart form (a file and its fields) and read the JSON answer. */
export async function apiForm<T = any>(path: string, form: FormData): Promise<T> {
  const res = await fetch(withBase(path), { method: "POST", body: form, credentials: "same-origin" });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export interface AppConfig {
  title: string;
  subtitle: string;
  version: string;
  auth_mode: "password" | "oauth" | "dual" | "none";
  oauth_providers: string[];
  allow_registration: boolean;
  enforce_consent: boolean;
  playground: boolean;
  experiment: string | null;
  docs_url: string;
}

export interface Me {
  user: string | null;
  display_name?: string;
  is_admin?: boolean;
  consented?: boolean;
  needs_consent?: boolean;
}
