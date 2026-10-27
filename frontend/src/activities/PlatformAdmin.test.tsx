import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { PlatformAdmin } from "./PlatformAdmin";

// A fake /platform API: made-up schools and teachers only.

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function fake() {
  const calls: { method: string; path: string; body?: any }[] = [];
  const schools = [{ id: "s1", udise_code: "99999999991", school_name: "Hill School", district: "D", state: "S",
                     admin_email: "hill@example.com", is_active: true, teachers: 1, teachers_active: 1, cards_saved: 12,
                     cards_failed: 1, last_upload_at: "2026-10-27T09:00:00Z" }];
  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname.replace("/api/v1", "");
    const method = init?.method || "GET";
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === "/platform/stats") return json({ schools: 1, schools_active: 1, teachers: 1, teachers_active: 1, uploads: 3,
      cards_saved: 12, cards_failed: 1, last_upload_at: null, activities_waiting: 2, activities_offered: 5 });
    if (path === "/platform/schools") return json(schools);
    if (path === "/platform/schools/s1/teachers") return json([{ id: "t1", teacher_name: "Asha Teacher", username: "asha",
      stages: ["Preparatory"], is_active: true, last_login: null, cards_saved: 12, cards_failed: 1 }]);
    if (path === "/platform/teachers/t1/password" && method === "POST") return json({ success: true });
    return json({ detail: "no fake" }, 404);
  };
  return { calls, fetch: fetchImpl };
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("Application admin", () => {
  it("shows totals, every school and its teachers, and sets a new password for a teacher", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetch));
    const user = userEvent.setup();
    render(<PlatformAdmin api={api} onLogout={vi.fn()} />);
    expect(await screen.findByText("Cards saved to PARAKH")).toBeInTheDocument();
    expect(screen.getByText("2 waiting for review")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Schools & teachers/ }));
    const row = (await screen.findByRole("rowheader", { name: /Hill School/ })).closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Teachers" }));
    const teacher = (await screen.findByRole("rowheader", { name: /Asha Teacher/ })).closest("tr")!;
    await user.click(within(teacher).getByRole("button", { name: /New password/ }));
    const dialog = await screen.findByRole("dialog", { name: "New password for Asha Teacher" });
    await user.type(within(dialog).getByLabelText("New password"), "newpass123");
    await user.type(within(dialog).getByLabelText("Type it again"), "newpass123");
    await user.click(within(dialog).getByRole("button", { name: "Set password" }));
    await waitFor(() => expect(f.calls.some((c) => c.path === "/platform/teachers/t1/password" && c.body.password === "newpass123")).toBe(true));
    expect(await screen.findByText(/New password set for Asha Teacher/)).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    vi.stubGlobal("fetch", vi.fn(fake().fetch));
    const { container } = render(<PlatformAdmin api={api} onLogout={vi.fn()} />);
    await screen.findByText("Cards saved to PARAKH");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
