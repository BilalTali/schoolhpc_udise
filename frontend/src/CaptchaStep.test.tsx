import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { CaptchaStep } from "./CaptchaStep";

// The server's answers are faked; nothing reaches PARAKH.

function fakeServer() {
  const calls: { path: string; body: any; headers: Headers }[] = [];
  let picture = 1;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, body, headers: new Headers(init?.headers) });
    const json = (status: number, b: unknown) => new Response(JSON.stringify(b), { status });
    if (path.endsWith("/new-captcha")) return json(200, { status: "captcha_required", captcha_image: `data:image/png;base64,P${++picture}` });
    if (path.endsWith("/verify-captcha")) {
      if (body.answer === "11") return json(200, { status: "authenticated", user: "Test Teacher" });
      if (body.answer === "22") return json(200, { status: "otp_required" });
      return json(200, { status: "captcha_required", captcha_image: `data:image/png;base64,P${++picture}`,
                         error: "That answer was not accepted. Please try this new picture." });
    }
    return json(404, {});
  }));
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("Typed PARAKH captcha", () => {
  it("shows PARAKH's picture, gives a new one after a wrong answer, then connects", async () => {
    const calls = fakeServer();
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<CaptchaStep who="teacher" image="data:image/png;base64,P1" onDone={onDone} onCancel={() => {}} />);
    const img = screen.getByRole("img", { name: /PARAKH login captcha/ });
    expect(img).toHaveAttribute("src", "data:image/png;base64,P1");
    expect(screen.getByLabelText("Answer")).toHaveFocus();

    await user.type(screen.getByLabelText("Answer"), "12{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("not accepted");
    expect(img).toHaveAttribute("src", "data:image/png;base64,P2");
    expect(screen.getByLabelText("Answer")).toHaveValue("");

    await user.type(screen.getByLabelText("Answer"), "11");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ status: "authenticated", user: "Test Teacher" }));
    const verify = calls.filter((c) => c.path.endsWith("/teacher/hpc/verify-captcha"));
    expect(verify.map((c) => c.body.answer)).toEqual(["12", "11"]);
    expect(verify[0].headers.get("X-Requested-With")).toBe("TeacherAssist");    // the CSRF header
  });

  it("passes the OTP step on, can fetch a new picture, and needs an answer", async () => {
    fakeServer();
    const onDone = vi.fn();
    const user = userEvent.setup();
    render(<CaptchaStep who="school" image="data:image/png;base64,P1" onDone={onDone} onCancel={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Connect" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Type the answer");
    await user.click(screen.getByRole("button", { name: /New picture/ }));
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "data:image/png;base64,P2"));
    await user.type(screen.getByLabelText("Answer"), "22{Enter}");
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ status: "otp_required" }));
  });

  it("has no axe violations", async () => {
    fakeServer();
    const { container } = render(<CaptchaStep who="teacher" image="data:image/png;base64,P1" onDone={() => {}} onCancel={() => {}} />);
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
