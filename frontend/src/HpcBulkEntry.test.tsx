import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HpcBulkEntry } from "./HpcCards";

const api = { base: "http://test/api/v1", token: "t", onUnauthorized: vi.fn() };
const OBSERVATION = { key: "b_observation", label: "Observational notes", kind: "text", options: [], max_len: 1300,
                      required: false, multiple: false,
                      suggestions: ["Worked well with friends and shared materials.", "Asked good questions.", "Needed some support."] };
const SELF = { key: "b_self_5", label: "Self-assessment: I am proud of my work", kind: "choice", options: ["Yes", "No", "Not sure"],
               max_len: null, required: true, multiple: false, suggestions: [] };
const STRENGTHS = { key: "b_strengths", label: "Areas of strength", kind: "multi", options: ["Curiosity", "Teamwork", "Focus"],
                    max_len: null, required: true, multiple: true, suggestions: [] };
const GRID = { key: "b_grid_awareness", label: "Progress grid: Awareness", kind: "multi", options: ["Learnt something new",
               "Attentive to detail", "Understood the activity", "Focused and engaged"], max_len: null, required: true,
               multiple: true, suggestions: [], mix_pool: ["Learnt something new", "Attentive to detail", "Understood the activity",
               "Focused and engaged"], mix_pick: 2 };
const FIELDS: Record<string, any> = { b_observation: OBSERVATION, b_self_5: SELF, b_strengths: STRENGTHS, b_grid_awareness: GRID };

function fake() {
  const calls: { method: string; path: string; body?: any }[] = [];
  const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path: url.pathname + url.search, body });
    if (url.pathname.endsWith("/fields")) {
      return json({ parts: [{ code: "A1", title: "Part A1", fields: [] },
                            { code: "B", title: "Part B - Activity", fields: [OBSERVATION, SELF, STRENGTHS, GRID] }] });
    }
    if (url.pathname.endsWith("/bulk") && method === "GET") {
      const field = FIELDS[url.searchParams.get("field") || ""];
      return json({ field: { ...field, part: "B", part_title: "Part B - Activity" }, read_at: null, check: null,
                    rows: ["1", "2", "3"].map((id) => ({ student_id: id, student_name: `STUDENT ${id}`, grade: "Grade 4", section: "A",
                                                    status: "PENDING", value: field.multiple ? [] : "Old note",
                                                    portal_value: "", in_draft: false })) });
    }
    if (url.pathname.endsWith("/bulk") && method === "PUT") return json({ saved: Object.keys(body.values), problems: {} });
    if (url.pathname.endsWith("/bulk-mix")) {
      return json({ applied: !!body.apply, students: 3, cells: 6,
                    fields: [{ key: "b_observation", label: "Observational notes", filled: 3 },
                             { key: "b_self_5", label: "Self-assessment: I am proud of my work", filled: 3 }],
                    skipped: [{ key: "b_strengths", label: "Areas of strength", reason: "several options can be ticked - fill it yourself" }] });
    }
    if (url.pathname.endsWith("/progress")) {
      const saved = calls.some((c) => c.method === "PUT" || (c.path.endsWith("/bulk-mix") && c.body?.apply));
      return json({ total: 3, fields: { b_observation: { filled: saved ? 3 : 1, required: false } } });
    }
    return json({});
  };
  return { calls, fetchImpl };
}

afterEach(() => vi.unstubAllGlobals());

describe("Part B answers on the Activities tab", () => {
  it("shows only Part B, offers suggestions, and 'Apply to all' replaces answers that are already filled", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetchImpl));
    const user = userEvent.setup();
    render(<HpcBulkEntry api={api} stage="Preparatory" parts={["B"]} title="Part B answers" />);
    const fieldList = await screen.findByRole("combobox", { name: "" }).catch(() => screen.getAllByRole("combobox")[0]);
    // the question says how many students are left, and "done" once everyone has an answer
    await waitFor(() => expect(within(fieldList).getByRole("option", { name: "Observational notes — 2 to fill" })).toBeInTheDocument());
    expect(within(fieldList).queryByRole("group", { name: "Part A1" })).not.toBeInTheDocument();
    await user.selectOptions(fieldList, "b_observation");
    await screen.findByText("STUDENT 1");

    // the fill box: pick a suggestion
    const pick = screen.getAllByRole("combobox", { name: "Observational notes: use a suggestion" })[0];
    await user.selectOptions(pick, "Worked well with friends and shared materials.");
    const save = screen.getByRole("button", { name: /to drafts/ });
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(save).toBeDisabled();                             // every student already has a note: nothing empty to fill
    await user.click(screen.getByRole("button", { name: "Apply to all" }));
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(f.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(f.calls.find((c) => c.method === "PUT")!.body).toEqual({
      field: "b_observation",
      values: { "1": "Worked well with friends and shared materials.", "2": "Worked well with friends and shared materials.",
                "3": "Worked well with friends and shared materials." } });
    await waitFor(() => expect(within(fieldList).getByRole("option", { name: "Observational notes — ✓ done" })).toBeInTheDocument());
  });

  it("'Mix suggestions' gives the students different suggestions, each about equally often", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetchImpl));
    const user = userEvent.setup();
    render(<HpcBulkEntry api={api} stage="Preparatory" parts={["B"]} title="Part B answers" />);
    const fieldList = screen.getAllByRole("combobox")[0];
    await waitFor(() => expect(within(fieldList).getAllByRole("option").length).toBeGreaterThan(1));
    await user.selectOptions(fieldList, "b_observation");
    await screen.findByText("STUDENT 1");
    await user.click(screen.getByRole("button", { name: "Mix suggestions" }));
    await user.click(screen.getByRole("button", { name: /to drafts/ }));
    await waitFor(() => expect(f.calls.some((c) => c.method === "PUT")).toBe(true));
    const given = Object.values(f.calls.find((c) => c.method === "PUT")!.body.values) as string[];
    expect(new Set(given)).toEqual(new Set(OBSERVATION.suggestions));     // 3 students, 3 suggestions: one each
  });

  it("Yes / No / Not sure questions can be mixed too; several-option questions are not", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetchImpl));
    const user = userEvent.setup();
    render(<HpcBulkEntry api={api} stage="Preparatory" parts={["B"]} title="Part B answers" />);
    const fieldList = screen.getAllByRole("combobox")[0];
    await waitFor(() => expect(within(fieldList).getAllByRole("option").length).toBeGreaterThan(3));
    await user.selectOptions(fieldList, "b_self_5");
    await screen.findByText("STUDENT 1");
    expect(screen.queryByRole("button", { name: "Mix suggestions" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mix answers" }));
    await user.click(screen.getByRole("button", { name: /to drafts/ }));
    await waitFor(() => expect(f.calls.some((c) => c.method === "PUT")).toBe(true));
    const given = Object.values(f.calls.find((c) => c.method === "PUT")!.body.values) as string[];
    expect(new Set(given)).toEqual(new Set(["Yes", "No", "Not sure"]));    // 3 students, 3 answers: one each

    await user.selectOptions(fieldList, "b_strengths");
    await screen.findByText("STUDENT 1");
    expect(screen.queryByRole("button", { name: /^Mix (answers|suggestions)$/ })).not.toBeInTheDocument();
  });

  it("'Mix all questions' fills every question on the screen at once and saves with one button", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetchImpl));
    const user = userEvent.setup();
    render(<HpcBulkEntry api={api} stage="Preparatory" parts={["B"]} title="Part B answers" />);
    await user.click(await screen.findByRole("button", { name: /Mix all questions/ }));
    expect(await screen.findByText(/Fills/)).toHaveTextContent("Fills 6 answers in 2 questions for 3 students");
    expect(screen.getByText(/Not mixed/)).toHaveTextContent("Areas of strength - several options can be ticked");
    const preview = f.calls.find((c) => c.path.endsWith("/bulk-mix"))!;
    expect(preview.body).toEqual({ fields: ["b_observation", "b_self_5", "b_strengths", "b_grid_awareness"], replace: false, apply: false });

    await user.click(screen.getByRole("checkbox", { name: "Replace answers already filled" }));
    await user.click(screen.getByRole("button", { name: /Mix all questions/ }));
    await user.click(await screen.findByRole("button", { name: /Save all/ }));
    expect(await screen.findByText("Saved 6 mixed answers for 3 students.")).toBeInTheDocument();
    const saved = f.calls.filter((c) => c.path.endsWith("/bulk-mix")).at(-1)!;
    expect(saved.body).toMatchObject({ replace: true, apply: true });
    const fieldList = screen.getAllByRole("combobox")[0];
    await waitFor(() => expect(within(fieldList).getByRole("option", { name: "Observational notes — ✓ done" })).toBeInTheDocument());
  });

  it("Part B's several-option assessment questions get a few different options per student", async () => {
    const f = fake();
    vi.stubGlobal("fetch", vi.fn(f.fetchImpl));
    const user = userEvent.setup();
    render(<HpcBulkEntry api={api} stage="Middle" parts={["B"]} title="Part B answers" />);
    const fieldList = screen.getAllByRole("combobox")[0];
    await waitFor(() => expect(within(fieldList).getAllByRole("option").length).toBeGreaterThan(4));
    await user.selectOptions(fieldList, "b_grid_awareness");
    await screen.findByText("STUDENT 1");
    await user.click(screen.getByRole("button", { name: "Mix answers" }));
    await user.click(screen.getByRole("button", { name: /to drafts/ }));
    await waitFor(() => expect(f.calls.some((c) => c.method === "PUT")).toBe(true));
    const given = Object.values(f.calls.find((c) => c.method === "PUT")!.body.values) as string[][];
    expect(given).toHaveLength(3);
    for (const v of given) {
      expect(v).toHaveLength(2);
      expect(new Set(v).size).toBe(2);
      expect(v.every((o) => GRID.mix_pool.includes(o))).toBe(true);
    }
  });
});
