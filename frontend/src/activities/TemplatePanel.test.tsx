import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { TemplatePanel } from "./TemplatePanel";
import { ClassSettings } from "./ClassSettings";

// Fake /teacher/template and /teacher/settings endpoints with synthetic students only.

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function student(id: string, ready: boolean, extra: Record<string, unknown> = {}) {
  return { student_id: id, student_name: `STUDENT ${id}`, grade: "Grade 5", section: "A", ready,
           part_b_problems: ready ? [] : ["No activity chosen for: Mathematics"], other_problems: [], fix: ready ? "" : "activities", ...extra };
}
function job(students: ReturnType<typeof student>[], status = "COMPLETED") {
  return { id: "j1", status, done: status === "RUNNING" ? 1 : students.length, total: students.length, seconds_left: 30,
           finished_at: "2026-10-26T09:30:00+00:00", error: null, ready: students.filter((s) => s.ready).length, students };
}

function fakeTemplate(initial: { job: unknown; settings_complete: boolean; settings_missing?: string[] }) {
  const state = { ...initial, settings_missing: initial.settings_missing || [], calls: [] as { method: string; path: string }[], afterPost: null as unknown,
                  precheck: { stage: "Preparatory", students: 2, complete: 2, items: [] } as unknown };
  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname.replace("/api/v1", "") + url.search;
    const method = init?.method || "GET";
    state.calls.push({ method, path });
    if (path === "/teacher/template/Preparatory/precheck") return json(200, state.precheck);
    if (path === "/teacher/template/Preparatory/check" && method === "GET")
      return json(200, { job: state.job, settings_complete: state.settings_complete, settings_missing: state.settings_missing });
    if (path === "/teacher/template/Preparatory/check" && method === "POST") {
      state.job = state.afterPost;
      return json(200, state.job);
    }
    if (path.startsWith("/teacher/template/Preparatory/download")) return Promise.resolve(new Response(new Blob(["xlsx"]), { status: 200 }));
    return json(404, { detail: "no fake" });
  };
  return { state, fetch: fetchImpl };
}

function setup(initial: Parameters<typeof fakeTemplate>[0], total = 3) {
  const fake = fakeTemplate(initial);
  vi.stubGlobal("fetch", vi.fn(fake.fetch));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
  const onFix = vi.fn();
  const onOpenSettings = vi.fn();
  const view = render(<TemplatePanel api={api} stage="Preparatory" total={total} onFix={onFix} onOpenSettings={onOpenSettings} />);
  return { fake, onFix, onOpenSettings, user: userEvent.setup(), ...view };
}

const downloadButton = () => screen.getByRole("button", { name: /Download template \(.* students\)$/ });
const downloads = (fake: ReturnType<typeof fakeTemplate>) => fake.state.calls.filter((c) => c.path.includes("/download"));

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("Template panel", () => {
  it("Save greyed out because nothing can be saved yet: says why, naming what blocks and how to fill it", async () => {
    const blocked = { ...job([student("1", true), student("2", true)]), complete: 0,
                      blocking: [{ problem: "Part A4 - Parent-Teacher Partnership: 'Any other' support is ticked", students: 2 }] };
    setup({ job: blocked, settings_complete: true });
    await screen.findByText(/Ready as of/);
    const save = screen.getByRole("button", { name: /Save ready students to PARAKH \(0\)/ });
    expect(save).toBeDisabled();
    const reason = document.getElementById(save.getAttribute("aria-describedby") || "")!;
    expect(reason).toHaveTextContent("0 can be saved: Part A4 - Parent-Teacher Partnership: 'Any other' support is ticked (2 students)");
    expect(reason).toHaveTextContent(/Global Mix or "Fix what is missing"/);
  });

  it("mixed class: counts ready students, lists the others with a reason and a Fix button", async () => {
    const { user, onFix, fake } = setup({ job: job([student("1", true), student("2", true), student("3", false)]), settings_complete: true });
    expect(await screen.findByText(/Ready as of/)).toHaveTextContent("2 of 3");
    expect(downloadButton()).toHaveTextContent("Download template (2 of 3 students)");
    expect(downloadButton()).toBeEnabled();
    const item = screen.getByText(/ID 3/).closest("li")!;
    expect(item).toHaveTextContent("No activity chosen for: Mathematics");
    await user.click(within(item).getByRole("button", { name: /Fix in Activities/ }));
    expect(onFix).toHaveBeenCalledWith("3", "activities", "STUDENT 3");
    await user.click(downloadButton());
    await waitFor(() => expect(downloads(fake)).toHaveLength(1));
    expect(downloads(fake)[0].path).toContain("include=ready");
    expect(downloads(fake)[0].path).not.toContain("confirmed");
  });

  it("zero ready: the download is disabled with the reason shown", async () => {
    setup({ job: job([student("1", false), student("2", false, { fix: "card", part_b_problems: ["Student's own answer missing"] })]), settings_complete: true });
    await screen.findByText(/Ready as of/);
    expect(downloadButton()).toHaveTextContent("(0 of 2 students)");
    expect(downloadButton()).toBeDisabled();
    expect(screen.getByText(/No student's Part B is complete yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Fix in the card/ })).toBeInTheDocument();
  });

  it("all ready: no not-ready list, download enabled", async () => {
    setup({ job: job([student("1", true), student("2", true)]), settings_complete: true });
    await screen.findByText(/Ready as of/);
    expect(downloadButton()).toHaveTextContent("(2 of 2 students)");
    expect(downloadButton()).toBeEnabled();
    expect(screen.queryByText(/Who is not ready/)).not.toBeInTheDocument();
  });

  it("settings not finished: download disabled and a link to Class settings", async () => {
    const { user, onOpenSettings } = setup({ job: job([student("1", true)]), settings_complete: false, settings_missing: ["Working days for May"] });
    expect(await screen.findByText(/class settings are not finished/)).toHaveTextContent("Working days for May");
    expect(downloadButton()).toBeDisabled();
    expect(screen.getByText("Finish the class settings first.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Class settings" }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("all students needs a confirmation, and Cancel sends nothing", async () => {
    const { user, fake } = setup({ job: job([student("1", true), student("2", false)]), settings_complete: true });
    await screen.findByText(/Ready as of/);
    await user.click(screen.getByRole("button", { name: /all students/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("1 student is not ready");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(downloads(fake)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: /all students/ }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Download all" }));
    await waitFor(() => expect(downloads(fake)).toHaveLength(1));
    expect(downloads(fake)[0].path).toContain("include=all&confirmed=true");
  });

  it("checking shows progress, then the result; no check means no download yet", async () => {
    const { user, fake } = setup({ job: null, settings_complete: true });
    expect(await screen.findByText("Check the class first.")).toBeInTheDocument();
    expect(downloadButton()).toHaveTextContent("(? of 3 students)");
    fake.state.afterPost = job([student("1", true), student("2", false), student("3", true)], "RUNNING");
    await user.click(screen.getByRole("button", { name: "Check the class" }));
    expect(await screen.findByRole("progressbar", { name: "Checking the class" })).toHaveAttribute("aria-valuenow", "1");
    fake.state.job = job([student("1", true), student("2", false), student("3", true)]);
    expect(await screen.findByText(/Ready as of/, {}, { timeout: 3000 })).toHaveTextContent("2 of 3");
    expect(fake.state.calls.filter((c) => c.method !== "GET")).toEqual([{ method: "POST", path: "/teacher/template/Preparatory/check" }]);
    expect(fake.state.calls.some((c) => c.path === "/teacher/template/Preparatory/precheck")).toBe(true);   // looked first
  });

  it("before checking it lists every empty answer with where to fix it, and starts only when asked", async () => {
    const { user, fake } = setup({ job: null, settings_complete: true });
    await screen.findByText("Check the class first.");
    fake.state.precheck = { stage: "Preparatory", students: 3, complete: 1, items: [
      { where: "Excel file - sheet 'Preparatory', column 'Mathematics: summative marks obtained'", part: "D - HPC Credit",
        question: "Mathematics: summative marks obtained",
        students: [{ student_id: "2", student_name: "STUDENT 2", grade: "Grade 5", section: "A" }] },
      { where: "Activities (tab 2) - Part B answers", part: "B - Activity", question: "Self-assessment: I am proud of my work",
        students: [{ student_id: "3", student_name: "STUDENT 3", grade: "Grade 4", section: "B" }] }] };
    fake.state.afterPost = job([student("1", true)], "RUNNING");
    await user.click(screen.getByRole("button", { name: "Check the class" }));
    const found = await screen.findByRole("region", { name: "Preparatory: before the check" });
    expect(found).toHaveTextContent("1 of 3 students have every required answer. 2 answers are empty");
    expect(found).toHaveTextContent("Excel file - sheet 'Preparatory', column 'Mathematics: summative marks obtained'");
    expect(found).toHaveTextContent("Activities (tab 2) - Part B answers");
    expect(found).toHaveTextContent("Grade 4 Sec B - STUDENT 3 (ID 3)");
    expect(fake.state.calls.some((c) => c.method === "POST")).toBe(false);      // nothing started yet
    await user.click(within(found).getByRole("button", { name: "Start the check anyway" }));
    await waitFor(() => expect(fake.state.calls.filter((c) => c.method === "POST")).toHaveLength(1));
    expect(screen.queryByRole("region", { name: "Preparatory: before the check" })).not.toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = setup({ job: job([student("1", true), student("2", false)]), settings_complete: true });
    await screen.findByText(/Ready as of/);
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------

const MONTHS = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"];

function settingsView(values: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  const v = { medium: "", rural_urban: "", working_days: Array(12).fill(null), max_marks: { "1": null, "2": null }, declaration: "", ...values };
  return { stage: "Preparatory", values: v, missing: ["Medium of instruction"], complete: false, version: 1, updated_at: null,
           marks_subjects: [{ n: "1", name: "Language 1" }, { n: "2", name: "Mathematics" }],
           months: MONTHS.map((name, i) => ({ key: `m${i}`, name, max: 31 })),
           choices: { medium: ["Hindi", "English"], rural_urban: ["Rural", "Urban"], loaded: true }, ...extra };
}

function setupSettings() {
  const state = { puts: [] as any[] };
  vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method || "GET";
    if (method === "GET") return json(200, settingsView());
    const body = JSON.parse(String(init!.body));
    state.puts.push(body);
    if (body.values.working_days[1] === 0) return json(422, { detail: { problems: { medium: "Choose one of the listed mediums." }, warnings: {} } });
    return json(200, { ...settingsView(body.values, { complete: true, missing: [], version: 2 }), warnings: { "working_days.0": "April: more than 26 days - please check." } });
  }));
  const onSaved = vi.fn();
  const view = render(<ClassSettings api={api} stage="Preparatory" onSaved={onSaved} />);
  return { state, onSaved, user: userEvent.setup(), ...view };
}

describe("Class settings", () => {
  it("fills months, applies the same marks to all, saves with the version and shows warnings", async () => {
    const { user, state, onSaved } = setupSettings();
    await user.selectOptions(await screen.findByLabelText("Medium of instruction"), "Hindi");
    await user.selectOptions(screen.getByLabelText("Rural / Urban"), "Rural");
    await user.type(screen.getByLabelText("April"), "27");
    await user.click(screen.getByRole("button", { name: "Copy April to every month" }));
    expect(screen.getByText(/Total for the year/)).toHaveTextContent("324");
    await user.type(screen.getByLabelText(/Same for every subject/), "50");
    await user.click(screen.getByRole("button", { name: "Apply to all" }));
    expect(screen.getByLabelText("Mathematics")).toHaveValue("50");
    await user.click(screen.getByRole("radio", { name: "Yes" }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText(/The Excel template can now be made/)).toBeInTheDocument();
    expect(state.puts[0]).toEqual({ version: 1, values: { medium: "Hindi", rural_urban: "Rural", declaration: "Yes",
      working_days: Array(12).fill(27), max_marks: { "1": 50, "2": 50 } } });
    expect(onSaved).toHaveBeenCalled();
    expect(screen.getByText(/more than 26 days/)).toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("blocks bad numbers before saving and shows the server's problems", async () => {
    const { user, state } = setupSettings();
    await user.type(await screen.findByLabelText("April"), "40");
    expect(screen.getByText("April: between 0 and 31.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    await user.clear(screen.getByLabelText("April"));
    await user.type(screen.getByLabelText("May"), "0");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Choose one of the listed mediums.")).toBeInTheDocument();
    expect(state.puts).toHaveLength(1);
  });

  it("has no axe violations", async () => {
    const { container } = setupSettings();
    await screen.findByLabelText("April");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("Global Mix shows that it is working until the class check ends", () => {
  it("covers the page with the step it is on: looking, mixing, checking - then it goes away", async () => {
    const fake = fakeTemplate({ job: null, settings_complete: true });
    let finishMix: () => void = () => {};
    let polls = 0;
    const mix = { seed: "s1", from_marks: 0, grid: { cells: 12, students: 3, skipped: [], no_activity: [] },
                  answers: { cells: 30, students: 3, skipped: [] } };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname.replace("/api/v1", "");
      if (path.endsWith("/global-mix")) {
        const body = JSON.parse(String(init?.body || "{}"));
        if (!body.apply) return json(200, mix);
        await new Promise<void>((r) => { finishMix = r; });            // the mix takes a while
        return json(200, mix);
      }
      if (path.endsWith("/check") && init?.method === "POST") return json(200, job([student("1", true)], "RUNNING"));
      if (path.endsWith("/check")) {
        polls += 1;
        const j = fake.state.calls.length && polls > 2 ? job([student("1", true)]) : polls > 1 ? job([student("1", true)], "RUNNING") : null;
        return json(200, { job: j, settings_complete: true, settings_missing: [] });
      }
      return json(404, { detail: "no fake" });
    }));
    fake.state.calls.push({ method: "x", path: "x" });
    render(<TemplatePanel api={api} stage="Preparatory" total={3} onFix={vi.fn()} onOpenSettings={vi.fn()} />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Global Mix/ }));
    const confirmBox = await screen.findByRole("alertdialog", { name: /fill every empty answer/ });
    expect(screen.queryByText("Global Mix in progress")).toBeNull();     // the question is answered without the panel
    await user.click(within(confirmBox).getByRole("button", { name: "Mix and fill" }));

    expect(await screen.findByText("Global Mix in progress")).toBeInTheDocument();
    expect(screen.getByText(/Step 2 of 3: mixing - filling 12 activity\/level cells and 30 answers/)).toBeInTheDocument();
    expect(screen.getByText(/Do not close or leave this page/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mixing…" })).toBeDisabled();

    finishMix();
    expect(await screen.findByText(/Step 3 of 3: checking the class/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Global Mix in progress")).toBeNull(), { timeout: 6000 });
    expect(screen.getByText(/Filled 12 activity\/level cells and 30 answers/)).toBeInTheDocument();
  }, 15000);
});
