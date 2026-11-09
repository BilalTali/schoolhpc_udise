import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// "Open as teacher" opens /?tab=teacher:<id>: that tab sends X-TA-Tab on every request (the server answers with the
// teacher's own session); an ordinary tab never does. Signing out there ends only the teacher tab.

type Sent = { path: string; tab: string | null };

function server() {
  const sent: Sent[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    sent.push({ path: String(url).replace("http://test/api/v1", ""), tab: new Headers(init?.headers).get("X-TA-Tab") });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }));
  return sent;
}

beforeEach(() => { vi.resetModules(); sessionStorage.clear(); window.history.replaceState(null, "", "/"); });
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

describe("the school's teacher tab", () => {
  it("is taken from the address once, then every request says which teacher this tab is", async () => {
    window.history.replaceState(null, "", "/?tab=teacher%3At-42&open=roster");
    const { apiFetch, teacherTab } = await import("./api");
    expect(teacherTab()).toBe("teacher:t-42");
    expect(window.location.search).toBe("?open=roster");            // the tab marker leaves the address
    const sent = server();
    await apiFetch("/auth/me", {}, "http://test/api/v1");
    await apiFetch("/teacher/roster/sync", { method: "POST" }, "http://test/api/v1");
    expect(sent.map((s) => s.tab)).toEqual(["teacher:t-42", "teacher:t-42"]);
  });

  it("survives a reload of that tab, and signing out there makes it an ordinary tab", async () => {
    sessionStorage.setItem("ta_tab", "teacher:t-42");                 // the same tab after a reload
    const { apiFetch, teacherTab } = await import("./api");
    const sent = server();
    await apiFetch("/auth/logout", { method: "POST" }, "http://test/api/v1");
    expect(sent[0].tab).toBe("teacher:t-42");                         // the server ends only the teacher tab
    expect(teacherTab()).toBeNull();
    await apiFetch("/auth/me", {}, "http://test/api/v1");
    expect(sent[1].tab).toBeNull();
  });

  it("an ordinary tab never sends it", async () => {
    const { apiFetch, teacherTab } = await import("./api");
    const sent = server();
    await apiFetch("/auth/me", {}, "http://test/api/v1");
    expect(teacherTab()).toBeNull();
    expect(sent[0].tab).toBeNull();
  });
});
