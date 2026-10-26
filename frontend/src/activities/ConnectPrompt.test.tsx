import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActivitiesGrid } from "./ActivitiesGrid";
import { OPEN_PARAKH_EVENT } from "./parakhConnect";

// Not connected to PARAKH (the server answers 409): a friendly card, not an error, and never a sign-out.

afterEach(() => { vi.unstubAllGlobals(); });

describe("Connect to PARAKH prompt", () => {
  it("shows instead of an error and opens the connection panel", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Not connected to PARAKH." }), { status: 409 })));
    const onUnauthorized = vi.fn();
    render(<ActivitiesGrid api={{ base: "http://test/api/v1", onUnauthorized }} stage="Preparatory" />);
    expect(await screen.findByRole("heading", { name: /Connect to PARAKH to see your class's activities/ })).toBeInTheDocument();
    const opened = vi.fn();
    window.addEventListener(OPEN_PARAKH_EVENT, opened);
    await userEvent.setup().click(screen.getByRole("button", { name: "Connect to PARAKH" }));
    expect(opened).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
    window.removeEventListener(OPEN_PARAKH_EVENT, opened);
  });
});
