import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { LevelsGrid } from "./LevelsGrid";

// A fake /teacher/hpc-cards/{stage}/levels with two synthetic students and two subjects.

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const FIELDS = (code: string) => ["Awareness", "Sensitivity", "Creativity"].map((a) => ({ key: `c_${code}_${a.toLowerCase()}`, ability: a }));

function setup() {
  const puts: any[] = [];
  const gets: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method || "GET";
    if (!String(input).includes("/teacher/hpc-cards/Preparatory/levels")) return json(404, { detail: "no fake" });
    gets.push(String(input));
    if (method === "PUT") {
      const body = JSON.parse(String(init!.body));
      puts.push(body);
      return json(200, { saved: Object.keys(body.values).filter((s) => s !== "2"), problems: body.values["2"] ? { "2": "Not saved" } : {} });
    }
    const values = Object.fromEntries([...FIELDS("PSLS1"), ...FIELDS("PSLS3")].map((f) => [f.key, ""]));
    return json(200, {
      read_at: "2026-10-26T09:00:00+00:00",
      options: ["Beginner", "Proficient", "Advanced"],
      subjects: [{ code: "PSLS1", name: "Language 1 (R1)", fields: FIELDS("PSLS1") }, { code: "PSLS3", name: "Mathematics", fields: FIELDS("PSLS3") }],
      rows: [
        { student_id: "1", student_name: "STUDENT ONE", grade: "Grade 5", section: "A", values: { ...values, c_PSLS1_awareness: "Advanced" }, portal: values, in_draft: [] },
        { student_id: "2", student_name: "STUDENT TWO", grade: "Grade 5", section: "A", values, portal: values, in_draft: [] },
      ],
    });
  }));
  const view = render(<LevelsGrid api={api} stage="Preparatory" />);
  return { puts, gets, user: userEvent.setup(), ...view };
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("Part C levels grid", () => {
  it("fills every empty level, keeps set ones, lets a few differ, and saves only changes", async () => {
    const { puts, user } = setup();
    const cell = await screen.findByRole("combobox", { name: "STUDENT ONE, Language 1 (R1), Awareness" });
    expect(cell).toHaveValue("Advanced");
    await user.selectOptions(screen.getByRole("combobox", { name: /Fill every empty level/ }), "Proficient");
    await user.click(screen.getByRole("button", { name: "Fill 11 empty" }));
    expect(cell).toHaveValue("Advanced");                                     // a level already set stays
    await user.selectOptions(screen.getByRole("combobox", { name: "STUDENT TWO, Mathematics, Creativity" }), "Beginner");
    expect(screen.getByText("11 unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Save levels/ }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(Object.keys(puts[0].values["1"])).toHaveLength(5);
    expect(puts[0].values["2"]).toMatchObject({ c_PSLS3_creativity: "Beginner", c_PSLS1_awareness: "Proficient" });
    expect(await screen.findByText(/Saved for 1 student\. 1 could not be saved/)).toBeInTheDocument();
    const two = screen.getByRole("rowheader", { name: /STUDENT TWO/ });
    expect(within(two).getByText("Not saved")).toBeInTheDocument();
    expect(screen.getByText("6 unsaved changes")).toBeInTheDocument();          // the student not saved keeps their edits
  });

  it("loads from the app's copy and reads PARAKH again only when asked", async () => {
    const { gets, user } = setup();
    expect(await screen.findByText(/Loaded from the app's copy, read from PARAKH on/)).toBeInTheDocument();
    expect(gets).toHaveLength(1);
    expect(gets[0]).not.toContain("refresh");
    await user.click(screen.getByRole("button", { name: /Read again from PARAKH/ }));
    await waitFor(() => expect(gets).toHaveLength(2));
    expect(gets[1]).toContain("refresh=true");
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByRole("combobox", { name: "STUDENT ONE, Language 1 (R1), Awareness" });
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
