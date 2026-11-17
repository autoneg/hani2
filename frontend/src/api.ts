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
