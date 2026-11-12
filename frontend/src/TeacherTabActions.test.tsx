import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TeacherTab } from "./TeacherTabActions";

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
afterEach(() => vi.unstubAllGlobals());

describe("Open as teacher - any teacher account", () => {
  it("opens the teacher tab, and saves the teacher's PARAKH login", async () => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname.replace("/api/v1", "");
      calls.push({ method: init?.method || "GET", path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const body = path.endsWith("/open-tab") ? { tab: "teacher:t9", has_parakh_login: false } : { has_parakh_login: true };
      return new Response(JSON.stringify(body), { status: 200 });
    });
    const tab = { location: { href: "" }, focus: vi.fn(), close: vi.fn() };
    vi.stubGlobal("open", vi.fn(() => tab));
    render(<TeacherTab api={api} teacherId="t9" name="Added By Hand" />);
    await userEvent.click(screen.getByRole("button", { name: /Open as teacher/ }));
    await waitFor(() => expect(tab.location.href).toBe("/?tab=teacher%3At9"));
    expect(calls[0]).toMatchObject({ method: "POST", path: "/school/teachers/t9/open-tab" });

    await userEvent.click(screen.getByRole("button", { name: /PARAKH login/ }));
    await userEvent.type(screen.getByLabelText("PARAKH login ID of Added By Hand"), "T7AFCD2");
    await userEvent.type(screen.getByLabelText("PARAKH password of Added By Hand"), "Secret#1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("PARAKH login saved.")).toBeTruthy());
    expect(calls[1]).toEqual({ method: "PUT", path: "/school/teachers/t9/parakh-login",
                               body: { hpc_login_id: "T7AFCD2", hpc_password: "Secret#1" } });
  });
});

describe("A switched-off teacher", () => {
  it("says so instead of offering a tab that would fail, and can be switched on", async () => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ method: init?.method || "GET", path: new URL(String(input)).pathname.replace("/api/v1", ""),
                   body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    const onSaved = vi.fn();
    render(<TeacherTab api={api} teacherId="t5" name="Off" active={false} onSaved={onSaved} />);
    expect(screen.queryByRole("button", { name: /Open as teacher/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Switch on" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls[0]).toEqual({ method: "PUT", path: "/school/teachers/t5", body: { is_active: true } });
  });
});
