import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { ActivitiesGrid } from "./ActivitiesGrid";
import type { GridData, GridStudent } from "./gridTypes";

// A fake /teacher/activities-grid with three synthetic students and two subjects.

const SUBJECTS = [{ code: "PSLS1", name: "Language 1 (R1)" }, { code: "PSLS3", name: "Mathematics" }];
const KEYS = SUBJECTS.flatMap((s) => [`b_act_${s.code}`, ...["awareness", "sensitivity", "creativity"].map((a) => `b_lvl_${s.code}_${a}`)]);

function student(id: string, name: string, values: Record<string, string> = {}, extra: Partial<GridStudent> = {}): GridStudent {
  const all = Object.fromEntries([...KEYS, "b_replace"].map((k) => [k, values[k] || ""]));
  return {
    student_id: id, student_name: name, grade: "Grade 5", section: "A", status: "PENDING", values: all,
    source: Object.fromEntries(Object.keys(all).map((k) => [k, values[k] ? "portal" : ""])) as GridStudent["source"],
    locked: false, replace: false, existing: [], missing_subjects: [], problems: [], notes: [], ready: false,
    draft_version: 0, saved_at: null, ...extra,
  };
}

function readiness(s: GridStudent): GridStudent {
  const missing = SUBJECTS.filter((x) => !s.values[`b_act_${x.code}`]).map((x) => x.name);
  const noLevels = KEYS.filter((k) => k.startsWith("b_lvl_") && !s.values[k]).length;
  const problems = s.locked && !s.replace ? s.problems : [
    ...(missing.length ? [`No activity chosen for: ${missing.join(", ")}`] : []),
    ...(noLevels ? ["Levels not chosen for some subjects"] : [])];
  return { ...s, problems, ready: problems.length === 0, missing_subjects: missing };
}

function fakeGrid() {
  const full = Object.fromEntries(KEYS.map((k) => [k, k.startsWith("b_act_") ? "P85" : "Proficient"]));
  const state = {
    students: [
      readiness(student("1", "STUDENT ONE")),
      readiness(student("2", "STUDENT TWO", full, { existing: [{ key: "P85", name: "Bank 85", label: "85: Pairs", subject_names: ["Language 1 (R1)", "Mathematics"], complete: true }] })),
      readiness(student("3", "STUDENT THREE", full, { locked: true, problems: [], notes: ["Kept exactly as it is on PARAKH (its activities share subjects)."] })),
    ],
    calls: [] as { method: string; path: string; body?: any }[],
  };
  const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
  const data = (): GridData => ({
    stage: "Preparatory", session: "2627", subjects: SUBJECTS,
    options: [{ key: "P85", label: "85: Pairs" }, { key: "P91", label: "91: Story" }], labels: { P85: "85: Pairs", P91: "91: Story" },
    students: state.students, grades: ["Grade 5 - A"],
    summary: { ready: state.students.filter((s) => s.ready).length, total: 3, locked: 1 },
  });
  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname.replace("/api/v1", "") + url.search;
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    state.calls.push({ method, path, body });
    if (method === "GET" && path.startsWith("/teacher/template/")) return json(200, { job: null, settings_complete: false, settings_missing: ["Medium of instruction"] });
    if (method === "GET") return json(200, data());
    const one = path.match(/^\/teacher\/activities-grid\/Preparatory\/(\d+)$/);
    if (method === "PUT" && one) {
      const s = state.students.find((x) => x.student_id === one[1])!;
      if (body.base_version !== s.draft_version) return json(409, { detail: "changed elsewhere" });
      const next = readiness({ ...s, values: { ...s.values, ...body.values }, draft_version: s.draft_version + 1,
                               replace: (body.values.b_replace ?? (s.replace ? "Yes" : "")) === "Yes" });
      state.students = state.students.map((x) => (x.student_id === s.student_id ? next : x));
      return json(200, next);
    }
    if (method === "POST" && path.endsWith("/quick-fill")) {
      const targets = state.students.filter((s) => !(s.locked && !s.replace));
      let cells = 0;
      for (const s of targets) for (const k of KEYS) if (k.startsWith("b_act_") && !s.values[k]) cells++;
      if (body.apply) {
        state.students = state.students.map((s) => (targets.includes(s)
          ? readiness({ ...s, values: { ...s.values, ...Object.fromEntries(KEYS.filter((k) => k.startsWith("b_act_") && !s.values[k]).map((k) => [k, body.activity_key])) } })
          : s));
      }
      return json(200, { applied: !!body.apply, cells, students: 1, kept: 4, subjects: SUBJECTS.map((s) => s.name),
                         skipped: [{ student_id: "3", student_name: "STUDENT THREE", reason: "Tick 'Replace' for this student first." }] });
    }
    return json(404, { detail: "no fake" });
  };
  return { state, fetch: fetchImpl };
}

const api = { base: "http://test/api/v1", token: "t", onUnauthorized: vi.fn() };

function setup() {
  const fake = fakeGrid();
  vi.stubGlobal("fetch", vi.fn(fake.fetch));
  const view = render(<ActivitiesGrid api={api} stage="Preparatory" />);
  return { fake, user: userEvent.setup(), ...view };
}

const puts = (fake: ReturnType<typeof fakeGrid>) => fake.state.calls.filter((c) => c.method === "PUT");

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("Activities grid", () => {
  it("shows every student with a status, subjects in groups and plain radio labels", async () => {
    setup();
    expect(await screen.findByText("STUDENT ONE")).toBeInTheDocument();
    expect(screen.getByText(/students ready/)).toHaveTextContent("2 of 3 students ready");   // locked one is kept, so ready
    expect(screen.getByRole("columnheader", { name: "Mathematics" })).toBeInTheDocument();
    const one = screen.getByRole("rowheader", { name: /STUDENT ONE/ }).closest("tr")!;
    expect(within(one).getByText("Needs work")).toBeInTheDocument();
    expect(within(one).getByRole("radiogroup", { name: "STUDENT ONE, Mathematics, Awareness" })).toBeInTheDocument();
    expect(within(one).getAllByRole("radio", { name: "Beginner" })).toHaveLength(6);
    const three = screen.getByRole("rowheader", { name: /STUDENT THREE/ }).closest("tr")!;
    expect(within(three).getByText("Locked")).toBeInTheDocument();
    expect(within(three).getByRole("combobox", { name: "STUDENT THREE, Mathematics, activity" })).toBeDisabled();
  });

  it("saves a student's choices on its own after a short pause, and shows the result", async () => {
    const { fake, user } = setup();
    await screen.findByText("STUDENT ONE");
    await user.selectOptions(screen.getByRole("combobox", { name: "STUDENT ONE, Language 1 (R1), activity" }), "P91");
    await user.click(within(screen.getByRole("radiogroup", { name: "STUDENT ONE, Language 1 (R1), Awareness" })).getByRole("radio", { name: "Advanced" }));
    await waitFor(() => expect(puts(fake)).toHaveLength(1), { timeout: 2000 });
    expect(puts(fake)[0].path).toBe("/teacher/activities-grid/Preparatory/1");
    expect(puts(fake)[0].body).toEqual({ values: { b_act_PSLS1: "P91", b_lvl_PSLS1_awareness: "Advanced" }, base_version: 0 });
    const row = screen.getByRole("rowheader", { name: /STUDENT ONE/ }).closest("tr")!;
    expect(await within(row).findByText("Saved")).toBeInTheDocument();
    // the next save names the version it started from
    await user.click(within(screen.getByRole("radiogroup", { name: "STUDENT ONE, Mathematics, Creativity" })).getByRole("radio", { name: "Beginner" }));
    await waitFor(() => expect(puts(fake)).toHaveLength(2), { timeout: 2000 });
    expect(puts(fake)[1].body.base_version).toBe(1);
  });

  it("explains what to fix and lets a locked student be replaced", async () => {
    const { fake, user } = setup();
    await screen.findByText("STUDENT ONE");
    await user.click(screen.getByRole("button", { name: "Details for STUDENT ONE" }));
    expect(screen.getByText(/No activity chosen for: Language 1 \(R1\), Mathematics/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Details for STUDENT THREE" }));
    expect(screen.getByText(/Kept exactly as it is on PARAKH/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Replace activities on PARAKH/ }));
    await waitFor(() => expect(puts(fake)).toHaveLength(1), { timeout: 2000 });
    expect(puts(fake)[0].body.values).toEqual({ b_replace: "Yes" });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "STUDENT THREE, Mathematics, activity" })).toBeEnabled());
  });

  it("fills the whole class with one activity after a preview", async () => {
    const { fake, user } = setup();
    await screen.findByText("STUDENT ONE");
    await user.selectOptions(screen.getByRole("combobox", { name: "Activity" }), "P85");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();       // preview first
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText(/Fills/)).toHaveTextContent("Fills 2 cells for 1 student");
    expect(screen.getByText(/Keeps 4 cells/)).toBeInTheDocument();
    expect(screen.getByText(/Skips STUDENT THREE/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("Filled 2 cells for 1 student.")).toBeInTheDocument();
    const apply = fake.state.calls.find((c) => c.path.endsWith("/quick-fill") && c.body.apply)!;
    expect(apply.body).toMatchObject({ activity_key: "P85", subjects: null, students: null, replace_filled: false, expected_cells: 2 });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "STUDENT ONE, Mathematics, activity" })).toHaveValue("P85"));
  });

  it("can fill only the ticked students, for one subject", async () => {
    const { fake, user } = setup();
    await screen.findByText("STUDENT ONE");
    await user.click(screen.getByRole("checkbox", { name: "Tick STUDENT ONE" }));
    await user.click(screen.getByRole("radio", { name: /Only the 1 ticked/ }));
    await user.click(screen.getByRole("radio", { name: "Only:" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Subject to fill" }), "PSLS3");
    await user.selectOptions(screen.getByRole("combobox", { name: "Activity" }), "P91");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText(/Fills/);
    const call = fake.state.calls.find((c) => c.path.endsWith("/quick-fill"))!;
    expect(call.body).toMatchObject({ activity_key: "P91", subjects: ["PSLS3"], students: ["1"] });
  });

  it("hides subjects and filters to students that need work", async () => {
    const { user } = setup();
    await screen.findByText("STUDENT ONE");
    await user.click(screen.getByText(/Show subjects/));
    await user.click(screen.getByRole("checkbox", { name: "Language 1 (R1)" }));
    expect(screen.queryByRole("columnheader", { name: "Language 1 (R1)" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Mathematics" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Only students that need work" }));
    expect(screen.queryByText("STUDENT TWO")).not.toBeInTheDocument();
    expect(screen.getByText("STUDENT ONE")).toBeInTheDocument();
  });

  it("sends a waiting change when the tab is left instead of losing it", async () => {
    const { fake, user, unmount } = setup();
    await screen.findByText("STUDENT ONE");
    await user.click(within(screen.getByRole("radiogroup", { name: "STUDENT ONE, Mathematics, Sensitivity" })).getByRole("radio", { name: "Proficient" }));
    unmount();                                                  // before the autosave delay
    await waitFor(() => expect(puts(fake)).toHaveLength(1));
    expect(puts(fake)[0].body.values).toEqual({ b_lvl_PSLS3_sensitivity: "Proficient" });
  });

  it("works with the keyboard: one tab stop per level group, arrow keys choose", async () => {
    const { fake, user } = setup();
    await screen.findByText("STUDENT ONE");
    const group = screen.getByRole("radiogroup", { name: "STUDENT ONE, Language 1 (R1), Awareness" });
    within(group).getByRole("radio", { name: "Beginner" }).focus();
    await user.keyboard(" ");
    await user.keyboard("{ArrowRight}");
    expect(within(group).getByRole("radio", { name: "Proficient" })).toBeChecked();
    await waitFor(() => expect(puts(fake).length).toBeGreaterThan(0), { timeout: 2000 });
    expect(puts(fake).at(-1)!.body.values.b_lvl_PSLS1_awareness).toBe("Proficient");
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText("STUDENT ONE");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" ")}`)).toEqual([]);
  });
});
