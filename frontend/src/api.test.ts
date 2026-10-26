import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./api";

// The 15-minute access cookie runs out; the refresh cookie renews it. A page reload checks /auth/me first.

afterEach(() => { vi.unstubAllGlobals(); });

function fakeServer(refreshWorks: boolean) {
  const calls: string[] = [];
  let renewed = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = String(url).replace("http://test/api/v1", "");
    calls.push(path);
    if (path === "/auth/refresh") {
      renewed = refreshWorks;
      return new Response(null, { status: refreshWorks ? 200 : 401 });
    }
    if (path === "/auth/login") return new Response(null, { status: 401 });
    return new Response(JSON.stringify({ id: "t1" }), { status: renewed ? 200 : 401 });
  }));
  return calls;
}

describe("apiFetch keeps a teacher logged in", () => {
  it("renews an expired cookie for the page-load check /auth/me, then retries once", async () => {
    const calls = fakeServer(true);
    const res = await apiFetch("/auth/me", {}, "http://test/api/v1");
    expect(res.status).toBe(200);
    expect(calls).toEqual(["/auth/me", "/auth/refresh", "/auth/me"]);
  });

  it("stays logged out when the refresh cookie is gone too", async () => {
    const calls = fakeServer(false);
    expect((await apiFetch("/auth/me", {}, "http://test/api/v1")).status).toBe(401);
    expect(calls).toEqual(["/auth/me", "/auth/refresh"]);
  });

  it("never renews for logging in", async () => {
    const calls = fakeServer(true);
    expect((await apiFetch("/auth/login", { method: "POST" }, "http://test/api/v1")).status).toBe(401);
    expect(calls).toEqual(["/auth/login"]);
  });
});
