// Every call to the backend goes through apiFetch: the session is an httpOnly cookie (nothing secret is
// kept in the browser's storage), non-GET requests carry the CSRF header the backend checks, and an
// expired 15-minute access cookie is renewed once with the refresh cookie before giving up.

// Set VITE_API_BASE to call another server; by default the Vite dev server forwards /api to the backend.
export const API_BASE: string = import.meta.env.VITE_API_BASE || "/api/v1";

const CSRF_HEADER = { name: "X-Requested-With", value: "TeacherAssist" };

export interface Api {
  base: string;
  onUnauthorized: () => void;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function errorText(data: any): string {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message;
  if (d?.problems) return Object.entries(d.problems).map(([k, v]) => `${k}: ${v}`).join("; ");
  if (Array.isArray(d)) return d.map((e) => e.msg || JSON.stringify(e)).join("; ");
  return "Something went wrong. Please try again.";
}

let refreshing: Promise<boolean> | null = null;

/** Renews the cookie session; several requests failing at once share one refresh. */
function refreshSession(base: string): Promise<boolean> {
  refreshing ||= fetch(`${base}/auth/refresh`, {
    method: "POST", credentials: "include", headers: { [CSRF_HEADER.name]: CSRF_HEADER.value },
  }).then((r) => r.ok).catch(() => false).finally(() => { refreshing = null; });
  return refreshing;
}

export async function apiFetch(path: string, init: RequestInit = {}, base: string = API_BASE): Promise<Response> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") headers.set(CSRF_HEADER.name, CSRF_HEADER.value);
  const send = () => fetch(`${base}${path}`, { ...init, headers, credentials: "include" });
  let res = await send();
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (await refreshSession(base)) res = await send();
  }
  return res;
}

export async function call<T>(api: Api, method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await apiFetch(path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }, api.base);
  } catch {
    throw new ApiError(0, "Could not reach the server. Check that it is running and try again.");
  }
  if (res.status === 401) api.onUnauthorized();
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, errorText(data), data?.detail);
  return data as T;
}

export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}
