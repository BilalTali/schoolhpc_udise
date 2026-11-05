import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchoolHome, UdiseCard } from "./SchoolHome";

const api = { base: "/api/v1", onUnauthorized: vi.fn() };
const services = (on: string[], checked: string[] = []) => ["dcf", "profile", "teacher", "sdms"].map((key) => ({
  key, name: key, connected: on.includes(key), checked: checked.includes(key),
  why: on.includes(key) ? "" : "UDISE+ asked to sign in again for this service" }));

function fakeServer(answers: Record<string, unknown>) {
  const sent: { path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace("/api/v1", "");
    sent.push({ path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify(answers[path]), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  return sent;
}

afterEach(() => vi.unstubAllGlobals());

describe("SchoolHome", () => {
  it("shows HPC and UDISE+ as two plain cards, each opening its area, with no links out", async () => {
    fakeServer({ "/school/udise/status": { connected: true, username: "school01", connected_at: "x", services: services(["sdms", "dcf"]) } });
    const onOpenHpc = vi.fn();
    const onOpenUdise = vi.fn();
    render(<SchoolHome api={api} onOpenHpc={onOpenHpc} onOpenUdise={onOpenUdise} teachers={3} students={120} />);
    await userEvent.click(screen.getByRole("button", { name: /HPC/ }));
    expect(onOpenHpc).toHaveBeenCalledOnce();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /UDISE\+/ }));
    expect(onOpenUdise).toHaveBeenCalledOnce();
    expect(screen.queryAllByRole("link")).toEqual([]);
    expect(screen.getByText("120")).toBeInTheDocument();
  });

  it("connects UDISE+: the person types the captcha, then each service shows its saved session", async () => {
    const sent = fakeServer({
      "/school/udise/status": { connected: false, username: "", connected_at: null, services: services([]) },
      "/school/udise/connect": { success: true, status: "captcha_required", captcha_image: "data:image/png;base64,AAAA" },
      "/school/udise/verify-captcha": { success: true, status: "authenticated", connected: true, username: "school01",
                                         services: services(["sdms", "dcf"]) },
    });
    render(<UdiseCard api={api} onOpenSdms={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: /Connect UDISE\+/ }));
    await userEvent.type(screen.getByLabelText("UDISE+ username"), "school01");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Next: captcha" }));
    expect(await screen.findByAltText(/UDISE\+ captcha/)).toBeInTheDocument();

    fakeServer({ "/school/udise/status": { connected: true, username: "school01", connected_at: "x", services: services(["sdms", "dcf"], ["sdms"]) },
                 "/school/udise/verify-captcha": { success: true, status: "authenticated", connected: true, username: "school01",
                                                    services: services(["sdms", "dcf"], ["sdms"]) } });
    await userEvent.type(screen.getByLabelText(/6 characters/), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/2 of 4 services connected/)).toBeInTheDocument();
    const sdms = screen.getByText("Student module (SDMS)").closest("li")!;
    expect(within(sdms).getByText("Connected (checked just now)")).toBeInTheDocument();   // UDISE+ answered
    const dcf = screen.getByText(/data capture/i).closest("li")!;
    expect(within(dcf).getByText(/Session saved - not checked/)).toBeInTheDocument();       // saved, not asked
    expect(screen.queryAllByRole("link")).toEqual([]);                  // no links out of the app
    expect(sent.find((s) => s.path === "/school/udise/connect")?.body).toEqual({ username: "school01", password: "secret" });
  });
});
