import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FixMissing } from "./FixMissing";

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const pupil = (id: string, problems: string[], ready = true) =>
  ({ student_id: id, student_name: `PUPIL ${id}`, grade: "Grade 5", section: "A", ready, other_problems: problems });
const NAME = "Part A1 - General Info & Attendance: Mother/Father/Guardian Name: required";
const MARKS = "HPC Credit: Mathematics: summative marks obtained: required";

afterEach(() => vi.unstubAllGlobals());

describe("Fix what is missing", () => {
  it("is not shown when nothing the school holds is missing", () => {
    const { container } = render(<FixMissing api={api} stage="Preparatory" students={[pupil("1", [])]} onDone={() => {}} />);
    expect(container.innerHTML).toBe("");
  });

  it("sends the typed names and the ranges, then checks again", async () => {
    const sent: unknown[] = [];
    vi.stubGlobal("fetch", async (_: RequestInfo | URL, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify({ names: 1, months: 2, marks: 1, problems: [] }), { status: 200 });
    });
    const onDone = vi.fn();
    render(<FixMissing api={api} stage="Preparatory" onDone={onDone}
                       students={[pupil("1", [NAME, MARKS]), pupil("2", [MARKS]), pupil("3", [NAME], false)]} />);
    expect(screen.getByText(/Name on the HPC card \(1 student\)/)).toBeTruthy();       // not-ready 3 is not offered
    await userEvent.selectOptions(screen.getByLabelText("Whose name for PUPIL 1"), "Mother");
    await userEvent.type(screen.getByLabelText("Name for PUPIL 1"), "Haleema Begum");
    await userEvent.click(screen.getByRole("button", { name: /Save into the School Register/ }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent[0]).toEqual({ names: { "1": { relation: "Mother", name: "Haleema Begum" } },
                              marks: { low: 25, high: 45 }, attendance: { low: 75, high: 95 } });
    expect(screen.getByText(/Saved 1 name, 1 marks and 2 months/)).toBeTruthy();
  });
});

describe("Fix what is missing - one name for all", () => {
  it("fills only the empty name boxes, then sends them", async () => {
    const sent: any[] = [];
    vi.stubGlobal("fetch", async (_: RequestInfo | URL, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify({ names: 2, months: 0, marks: 0, problems: [] }), { status: 200 });
    });
    render(<FixMissing api={api} stage="Preparatory" onDone={() => {}}
                       students={[pupil("1", [NAME]), pupil("2", [NAME]), pupil("3", [NAME])]} />);
    await userEvent.type(screen.getByLabelText("Name for PUPIL 2"), "Own Name");
    await userEvent.selectOptions(screen.getByLabelText("Whose name, for all"), "Guardian");
    await userEvent.type(screen.getByLabelText("Name, for all"), "Bashir Ahmad");
    await userEvent.click(screen.getByRole("button", { name: "Apply to all empty" }));
    expect((screen.getByLabelText("Name for PUPIL 1") as HTMLInputElement).value).toBe("Bashir Ahmad");
    expect((screen.getByLabelText("Name for PUPIL 2") as HTMLInputElement).value).toBe("Own Name");   // kept
    await userEvent.click(screen.getByRole("checkbox", { name: /Missing days present/ }));
    await userEvent.click(screen.getByRole("button", { name: /Save into the School Register/ }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0].names).toEqual({ "1": { relation: "Guardian", name: "Bashir Ahmad" },
                                    "2": { relation: "Father", name: "Own Name" },
                                    "3": { relation: "Guardian", name: "Bashir Ahmad" } });
  });
});
