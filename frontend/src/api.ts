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

const NO_RENEW = ["/auth/login", "/auth/refresh", "/auth/logout", "/auth/school/register"];

// A teacher tab the school opened ("Open as teacher" -> /?tab=teacher:<id>): this tab sends X-TA-Tab on every
// request and the server answers it with the teacher's own session; the school's tab keeps the school's session.
// Kept in sessionStorage, so it belongs to this one tab (a reload keeps it, other tabs never see it).
const TAB_KEY = "ta_tab";
const TAB_HEADER = "X-TA-Tab";
function readTab(): string | null {
  try {
    const q = new URLSearchParams(window.location.search);
    const asked = q.get("tab");
    if (asked && asked.startsWith("teacher:")) {
      sessionStorage.setItem(TAB_KEY, asked);
      q.delete("tab");
      const rest = q.toString();
      window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
    }
    return sessionStorage.getItem(TAB_KEY);
  } catch {
    return null;
  }
}
let tab: string | null = typeof window !== "undefined" ? readTab() : null;
/** "teacher:<id>" in a teacher tab the school opened, else null. */
export const teacherTab = (): string | null => tab;
function leaveTab() {
  tab = null;
  try { sessionStorage.removeItem(TAB_KEY); } catch { /* storage blocked: the tab mode ends with the page */ }
}

let refreshing: Promise<boolean> | null = null;

/** Renews the cookie session; several requests failing at once share one refresh. */
function refreshSession(base: string): Promise<boolean> {
  const headers: Record<string, string> = { [CSRF_HEADER.name]: CSRF_HEADER.value };
  if (tab) headers[TAB_HEADER] = tab;
  refreshing ||= fetch(`${base}/auth/refresh`, {
    method: "POST", credentials: "include", headers,
  }).then((r) => r.ok).catch(() => false).finally(() => { refreshing = null; });
  return refreshing;
}

export async function apiFetch(path: string, init: RequestInit = {}, base: string = API_BASE): Promise<Response> {
  const method = (init.method || "GET").toUpperCase();
  if (tab && (path.startsWith("/auth/login") || path.startsWith("/auth/school/register"))) leaveTab();   // signing in here: an ordinary tab again
  const headers = new Headers(init.headers);
  if (method !== "GET" && method !== "HEAD") headers.set(CSRF_HEADER.name, CSRF_HEADER.value);
  if (tab) headers.set(TAB_HEADER, tab);
  const send = () => fetch(`${base}${path}`, { ...init, headers, credentials: "include" });
  let res = await send();
  if (tab && path.startsWith("/auth/logout")) leaveTab();             // the teacher tab signed out: only it ended
  // Renew and retry once - also for /auth/me, the check on page load (the 15-minute cookie may have gone);
  // never for logging in, out or renewing itself.
  if (res.status === 401 && !NO_RENEW.some((p) => path.startsWith(p))) {
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
