import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AllStagesDownload } from "./AllStagesDownload";

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const done = (ready: number, total: number) => ({ status: "COMPLETED", done: total, total, ready });

afterEach(() => { vi.unstubAllGlobals(); });

describe("One file for all stages", () => {
  it("leaves out empty stages, waits for every check and settings, then downloads the combined file", async () => {
    const state: Record<string, any> = {
      Foundational: { job: null, settings_complete: false, students: 0 },
      Preparatory: { job: done(8, 22), settings_complete: true, students: 22 },
      Middle: { job: null, settings_complete: true, students: 35 },
    };
    const calls: string[] = [];
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace("http://test/api/v1", "");
      calls.push(`${init?.method || "GET"} ${path}`);
      const stage = path.split("/")[3];
      if (path.endsWith("/precheck")) return json({ stage, students: 35, complete: 35, items: [] });
      if (path.endsWith("/check") && init?.method === "POST") { state[stage].job = done(30, 35); return json(state[stage].job); }
      if (path.endsWith("/check")) return json(state[stage]);
      if (path === "/teacher/template/all/download") return Promise.resolve(new Response(new Blob(["x"]), { status: 200 }));
      return Promise.resolve(new Response("{}", { status: 404 }));
    }));
    const user = userEvent.setup();
    render(<AllStagesDownload api={api} stages={["Foundational", "Preparatory", "Middle"]} onOpenSettings={vi.fn()} />);
    const list = await screen.findByRole("list");
    await waitFor(() => expect(within(list).getByText("8 of 22 ready")).toBeInTheDocument());
    expect(within(list).queryByText("Foundational")).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: /Download one file for all stages/ });
    expect(button).toBeDisabled();
    await user.click(within(within(list).getByText("Middle").closest("li")!).getByRole("button", { name: "Check" }));
    await waitFor(() => expect(button).toBeEnabled());
    expect(button).toHaveTextContent("(38 students)");
    await user.click(button);
    await waitFor(() => expect(calls).toContain("GET /teacher/template/all/download"));
  });
});
