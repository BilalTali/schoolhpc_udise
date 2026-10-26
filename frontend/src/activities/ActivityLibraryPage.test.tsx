import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import axe from "axe-core";
import { ActivityLibraryPage } from "./ActivityLibraryPage";
import { fakeLibraryApi } from "../test/fakeLibraryApi";
import type { Activity } from "./types";

const api = { base: "http://test/api/v1", token: "t", onUnauthorized: vi.fn() };

function setup({ isAdmin = true, activities }: { isAdmin?: boolean; activities?: Activity[] } = {}) {
  const fake = fakeLibraryApi({ isAdmin, activities });
  vi.stubGlobal("fetch", vi.fn(fake.fetch));
  const router = createMemoryRouter(
    [{ path: "/activities/:stage?", element: <ActivityLibraryPage api={api} isAdmin={isAdmin} /> },
     { path: "/", element: <a href="/activities/preparatory">Home</a> }],
    { initialEntries: ["/activities/preparatory"] });
  const view = render(<RouterProvider router={router} />);
  return { fake, router, user: userEvent.setup(), ...view };
}

const rows = () => screen.getAllByRole("row").slice(1);       // skip the header row
const calls = (fake: ReturnType<typeof fakeLibraryApi>, method: string, path: string) =>
  fake.state.calls.filter((c) => c.method === method && c.path.startsWith(path));

async function noAxeViolations(node: Element) {
  // jsdom cannot compute colours, so contrast is checked by hand (see library.css), not here.
  const result = await axe.run(node, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" ")}`)).toEqual([]);
}

beforeEach(() => vi.useRealTimers());
afterEach(() => vi.unstubAllGlobals());

describe("Activity Library table", () => {
  it("lists activities with plain coverage badges and counts", async () => {
    setup();
    expect(await screen.findByRole("button", { name: "L1CG 1, C 1.1" })).toBeInTheDocument();
    expect(rows()).toHaveLength(3);
    expect(within(rows()[0]).getByText("Covers all subjects")).toBeInTheDocument();
    expect(within(rows()[1]).getByText(/Missing: Mathematics, Art Education/)).toBeInTheDocument();
    expect(within(rows()[2]).getByText(/Has pictures - choose it on the PARAKH website/)).toBeInTheDocument();
    const counts = screen.getByText("Offered in Excel").parentElement!;
    expect(within(counts).getByText("2")).toBeInTheDocument();
  });

  it("searches after typing pauses and filters by coverage", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: "L1CG 1, C 1.1" });
    await user.type(screen.getByLabelText("Search activities"), "mcg");
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(calls(fake, "GET", "/activity-library?").at(-1)!.path).toContain("q=mcg");
    // one request for the finished word, not one per letter
    expect(calls(fake, "GET", "/activity-library?").filter((c) => c.path.includes("q=")).length).toBe(1);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(rows()).toHaveLength(3));
    await user.selectOptions(screen.getByLabelText("Covers all subjects"), "no");
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(calls(fake, "GET", "/activity-library?").at(-1)!.path).toContain("covers_all=false");
    expect(screen.getByRole("button", { name: "MCG 1, C 1.2" })).toBeInTheDocument();
  });

  it("shows a clear message when nothing matches, and when loading fails", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: "L1CG 1, C 1.1" });
    await user.type(screen.getByLabelText("Search activities"), "zzz");
    const none = await screen.findByRole("heading", { name: "No activities match" });

    fake.state.failList = 1;
    await user.click(within(none.parentElement!).getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is busy.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "L1CG 1, C 1.1" })).toBeInTheDocument();
  });

  it("shows an empty library with a way forward", async () => {
    setup({ activities: [] });
    expect(await screen.findByRole("heading", { name: "No Preparatory activities yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Add your own activity/ }).length).toBeGreaterThan(0);
  });
});

describe("Managing activities (school admin)", () => {
  it("turns one activity off with its switch", async () => {
    const { fake, user } = setup();
    const sw = await screen.findByRole("switch", { name: "Offer L1CG 1, C 1.1 in Excel" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    await user.click(sw);
    await waitFor(() => expect(screen.getByRole("switch", { name: "Offer L1CG 1, C 1.1 in Excel" })).toHaveAttribute("aria-checked", "false"));
    expect(calls(fake, "PATCH", "/activity-library/a1")[0].body).toEqual({ status: "disabled" });
    expect(screen.getByRole("status")).toHaveTextContent("will no longer be offered in Excel");
  });

  it("turns several off at once after confirming", async () => {
    const { fake, user } = setup();
    await user.click(await screen.findByRole("checkbox", { name: "Select L1CG 1, C 1.1" }));
    await user.click(screen.getByRole("checkbox", { name: "Select MCG 1, C 1.2" }));
    await user.click(screen.getByRole("button", { name: "Turn off" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Turn off 2 activities?" });
    await user.click(within(dialog).getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(calls(fake, "POST", "/activity-library/bulk")).toHaveLength(1));
    expect(calls(fake, "POST", "/activity-library/bulk")[0].body).toEqual({ ids: ["a1", "a2"], action: "disable" });
    expect(await screen.findByText("2 activities turned off.")).toBeInTheDocument();
  });

  it("warns before making an activity that misses subjects the default", async () => {
    const { fake, user } = setup();
    await user.click(await screen.findByRole("button", { name: /Make default \(MCG 1, C 1.2\)/ }));
    const dialog = await screen.findByRole("alertdialog", { name: "This activity does not cover every subject" });
    expect(dialog).toHaveTextContent("Mathematics, Art Education");
    await user.click(within(dialog).getByRole("button", { name: "Make default anyway" }));
    await waitFor(() => expect(fake.state.defaultId).toBe("a2"));
    expect(calls(fake, "PUT", "/activity-library/defaults")[1].body).toEqual({ activity_id: "a2", confirm_partial: true });
    expect(await screen.findByText(/is now the default for Preparatory/)).toBeInTheDocument();
    expect(within(rows()[0]).getByText("Default")).toBeInTheDocument();     // default listed first
  });

  it("edits, warns about unsaved changes, saves only what changed, and resets", async () => {
    const { fake, user } = setup();
    await user.click(await screen.findByRole("button", { name: "L1CG 1, C 1.1" }));
    const dialog = await screen.findByRole("dialog", { name: "L1CG 1, C 1.1" });
    const text = within(dialog).getByLabelText("How the activity is done");
    await user.clear(text);
    await user.type(text, "Our version.");
    expect(within(dialog).getByText("Unsaved changes")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    const ask = await screen.findByRole("alertdialog", { name: "Discard changes?" });
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "L1CG 1, C 1.1" })).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls(fake, "PATCH", "/activity-library/a1")).toHaveLength(1));
    expect(calls(fake, "PATCH", "/activity-library/a1")[0].body).toEqual({ activity_text: "Our version.", version: 1 });
    expect(await within(dialog).findByRole("heading", { name: /Changes compared with PARAKH/ })).toBeInTheDocument();
    expect(within(dialog).queryByText("Unsaved changes")).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /Go back to original/ }));
    const sure = await screen.findByRole("alertdialog", { name: "Go back to the PARAKH original?" });
    await user.click(within(sure).getByRole("button", { name: "Go back to original" }));
    await waitFor(() => expect(calls(fake, "POST", "/activity-library/a1/reset")).toHaveLength(1));
    expect(await within(dialog).findByLabelText("How the activity is done")).toHaveValue("Pairs act out a conversation.");
  });

  it("asks before leaving the page with unsaved changes", async () => {
    const { router, user } = setup();
    await user.click(await screen.findByRole("button", { name: "L1CG 1, C 1.1" }));
    const dialog = await screen.findByRole("dialog", { name: "L1CG 1, C 1.1" });
    await user.type(within(dialog).getByLabelText("How the activity is done"), " more");
    router.navigate("/");
    const ask = await screen.findByRole("alertdialog", { name: "Leave without saving?" });
    await user.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(router.state.location.pathname).toBe("/activities/preparatory");
  });
});

describe("Adding activities", () => {
  it("needs a name, defaults to every subject, and a teacher must agree before sharing", async () => {
    const { fake, user } = setup({ isAdmin: false });
    await user.click((await screen.findAllByRole("button", { name: /Add your own activity/ }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New Preparatory activity" });
    const add = within(dialog).getByRole("button", { name: "Add activity" });
    expect(add).toBeDisabled();
    expect(within(dialog).getAllByRole("checkbox").filter((c) => (c as HTMLInputElement).checked)).toHaveLength(7);

    await user.type(within(dialog).getByLabelText(/Activity name/), "Story circle");
    expect(add).toBeEnabled();
    await user.click(within(dialog).getByRole("radio", { name: /My school/ }));
    expect(add).toBeDisabled();
    expect(within(dialog).getByText(/Tick the sharing agreement/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox", { name: /I made this activity myself/ }));
    await user.click(add);
    await waitFor(() => expect(calls(fake, "POST", "/activity-library")).toHaveLength(1));
    const body = calls(fake, "POST", "/activity-library")[0].body;
    expect(body).toMatchObject({ stage: "Preparatory", title: "Story circle", share: "school", consent: true });
    expect(body.subjects).toHaveLength(7);
    expect(await screen.findByText(/"Story circle" was added\. Before it can be chosen for students it still needs: Curricular goal, Competency/)).toBeInTheDocument();
  });

  it("a teacher's own activity picks goal and competency codes from PARAKH's and can then be used", async () => {
    const { fake, user } = setup({ isAdmin: false });
    await user.click((await screen.findAllByRole("button", { name: /Add your own activity/ }))[0]);
    const dialog = await screen.findByRole("dialog", { name: "New Preparatory activity" });
    await user.type(within(dialog).getByLabelText(/Activity name/), "Story circle");
    await user.selectOptions(await within(dialog).findByLabelText("Curricular goal code(s)"), "CG1");
    expect(within(dialog).getByRole("list", { name: /Curricular goal code\(s\) chosen/ })).toHaveTextContent("CG1");
    expect(within(dialog).getByLabelText("Curricular goal code(s)")).not.toHaveTextContent(/^CG1 \(/);   // not offered twice
    await user.selectOptions(within(dialog).getByLabelText("Competency code(s)"), "C1.1");
    await user.click(within(dialog).getByRole("button", { name: "Add activity" }));
    await waitFor(() => expect(fake.state.created).not.toBeNull());
    expect(fake.state.created).toMatchObject({ goals: ["CG1"], competencies: ["C1.1"] });
    expect(fake.state.created.approaches).toBeUndefined();                       // Preparatory: no approach
    expect(await screen.findByText(/"Story circle" was added and can now be chosen on the Activities tab/)).toBeInTheDocument();
  });

  it("a teacher edits a PARAKH activity as their own version, and can remove it again", async () => {
    const { fake, user } = setup({ isAdmin: false });
    await user.click(await screen.findByRole("button", { name: "L1CG 1, C 1.1" }));
    const dialog = await screen.findByRole("dialog", { name: "L1CG 1, C 1.1" });
    expect(within(dialog).getByText(/used on your own students' cards only/)).toBeInTheDocument();
    const assess = within(dialog).getByLabelText("How it is assessed");
    await user.clear(assess);
    await user.type(assess, "Ask: what would you say?");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls(fake, "PATCH", "/activity-library/a1")).toHaveLength(1));
    expect(calls(fake, "PATCH", "/activity-library/a1")[0].body).toEqual({ assessment_text: "Ask: what would you say?", version: 1 });
    expect(await within(dialog).findByText("Your version")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /Remove my version/ }));
    const sure = await screen.findByRole("alertdialog", { name: "Remove your version?" });
    await user.click(within(sure).getByRole("button", { name: "Remove my version" }));
    await waitFor(() => expect(calls(fake, "POST", "/activity-library/a1/reset")).toHaveLength(1));
    await waitFor(() => expect(within(dialog).queryByText("Your version")).not.toBeInTheDocument());
  });

  it("teachers see no admin controls", async () => {
    setup({ isAdmin: false });
    await screen.findByRole("button", { name: "L1CG 1, C 1.1" });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Make default/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Copy/ })).toHaveLength(3);
  });
});

describe("Getting activities from PARAKH", () => {
  it("shows progress, then the result, and stops checking after leaving the page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { fake, unmount } = setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(await screen.findByRole("button", { name: "Update Preparatory" }));
    expect(await screen.findByRole("progressbar", { name: "Sync progress" })).toBeInTheDocument();
    expect(calls(fake, "POST", "/activity-library/sync")[0].body).toEqual({ stage: "Preparatory" });
    await vi.advanceTimersByTimeAsync(1600);
    await vi.advanceTimersByTimeAsync(1600);
    expect(await screen.findByText(/2 new, 1 changed on PARAKH, 1 no longer on PARAKH/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();

    // start another, leave the page, and make sure nothing keeps polling
    await user.click(screen.getByRole("button", { name: "Update all stages" }));
    await screen.findByRole("progressbar");
    const before = calls(fake, "GET", "/activity-library/sync/").length;
    unmount();
    await vi.advanceTimersByTimeAsync(10000);
    expect(calls(fake, "GET", "/activity-library/sync/").length).toBe(before);
  });
});

describe("Accessibility and keyboard use", () => {
  it("has no axe violations on the page or in the editor", async () => {
    const { container, user } = setup();
    await screen.findByRole("button", { name: "L1CG 1, C 1.1" });
    await noAxeViolations(container);
    await user.click(screen.getByRole("button", { name: "L1CG 1, C 1.1" }));
    await noAxeViolations(await screen.findByRole("dialog"));
  });

  it("works with the keyboard only: open, move inside, close, and focus returns", async () => {
    const { user } = setup();
    const open = await screen.findByRole("button", { name: "L1CG 1, C 1.1" });
    open.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "L1CG 1, C 1.1" });
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    for (let i = 0; i < 40; i++) await user.tab();           // focus never leaves the dialog
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "L1CG 1, C 1.1" }));

    const sw = screen.getByRole("switch", { name: "Offer MCG 1, C 1.2 in Excel" });
    sw.focus();
    await user.keyboard(" ");
    await waitFor(() => expect(screen.getByRole("switch", { name: "Offer MCG 1, C 1.2 in Excel" })).toHaveAttribute("aria-checked", "false"));
  });
});
