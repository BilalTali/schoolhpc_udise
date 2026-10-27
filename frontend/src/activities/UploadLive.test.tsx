import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { UploadLive } from "./UploadLive";

// A fake /teacher/upload/jobs/{id}/live that moves through a job: synthetic students only.

const api = { base: "http://test/api/v1", onUnauthorized: vi.fn() };
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const at = "2026-10-26T12:00:00Z";
const student = (id: string, name: string, status: string, error: string | null = null) => ({ student_id: id, student_name: name, status, error });

function frames() {
  const base = { job_id: "job12345abc", total_students: 3, created_at: "2026-10-26T12:00:00", completed_at: null };
  return [
    { ...base, status: "IN_PROGRESS", success_count: 1, failed_count: 0,
      current: { student_id: "2", student_name: "STUDENT TWO", step: "Saving Part C (5 of 6)", since: at },
      events: [{ at, student_id: "1", student_name: "STUDENT ONE", text: "Saved to PARAKH", kind: "saved" },
               { at, student_id: "2", student_name: "STUDENT TWO", text: "Saving Part C (5 of 6)", kind: "step" }],
      students: [student("1", "STUDENT ONE", "SUCCESS"), student("2", "STUDENT TWO", "IN_PROGRESS"), student("3", "STUDENT THREE", "PENDING")] },
    { ...base, status: "PARTIAL_SUCCESS", success_count: 2, failed_count: 1, completed_at: "2026-10-26T12:00:30", current: null,
      events: [{ at, student_id: "3", student_name: "STUDENT THREE", text: "Not saved: Part C: Mathematics: Awareness: required", kind: "failed" }],
      students: [student("1", "STUDENT ONE", "SUCCESS"), student("2", "STUDENT TWO", "SUCCESS"),
                 student("3", "STUDENT THREE", "FAILED", "Part C: Mathematics: Awareness: required")] },
  ];
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("Upload live view", () => {
  it("mirrors the job: who and which step now, every student's state, then the outcome", async () => {
    const seq = frames();
    vi.stubGlobal("fetch", vi.fn(() => json(seq.length > 1 ? seq.shift() : seq[0])));
    const onFinished = vi.fn();
    render(<UploadLive api={api} jobId="job12345abc" onFinished={onFinished} />);

    expect(await screen.findByText("Saving to PARAKH…")).toBeInTheDocument();
    expect(screen.getByText(/— Saving Part C \(5 of 6\)…/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Students done" })).toHaveAttribute("aria-valuenow", "1");
    const two = screen.getByRole("row", { name: /STUDENT TWO/ });
    expect(within(two).getByText("Working…")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /STUDENT THREE/ })).getByText("Waiting")).toBeInTheDocument();

    expect(await screen.findByText("Finished, with some not saved", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("2 saved")).toBeInTheDocument();
    const three = screen.getByRole("row", { name: /STUDENT THREE/ });
    expect(within(three).getByText("Not saved")).toBeInTheDocument();
    expect(within(three).getByText("Part C: Mathematics: Awareness: required")).toBeInTheDocument();
    await waitFor(() => expect(onFinished).toHaveBeenCalledTimes(1));
    expect(onFinished.mock.calls[0][0].status).toBe("PARTIAL_SUCCESS");
    expect(screen.getByRole("button", { name: /Download the report/ })).toBeInTheDocument();
  });

  it("retries only the students PARAKH did not take, and says which need the file fixed", async () => {
    const finished = {
      job_id: "job12345abc", total_students: 3, created_at: "2026-10-26T12:00:00", completed_at: "2026-10-26T12:00:30",
      status: "PARTIAL_SUCCESS", success_count: 1, failed_count: 2, current: null, events: [],
      students: [student("1", "STUDENT ONE", "SUCCESS"), student("2", "STUDENT TWO", "FAILED", "Part A1 saved; Part A2 failed: PARAKH did not answer"),
                 student("3", "STUDENT THREE", "INVALID", "Part A1: Mother Tongue: required")],
    };
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method || "GET"} ${url}`);
      return url.endsWith("/retry") ? json({ job_id: "job99999new" }) : json(finished);
    }));
    const onRetry = vi.fn();
    render(<UploadLive api={api} jobId="job12345abc" onFinished={vi.fn()} onRetry={onRetry} />);
    const button = await screen.findByRole("button", { name: /Retry the 1 not saved because of PARAKH/ });
    expect(screen.getByText(/1 need a fix in the file first/)).toBeInTheDocument();
    button.click();
    await waitFor(() => expect(onRetry).toHaveBeenCalledWith("job99999new"));
    expect(calls).toContain("POST http://test/api/v1/teacher/upload/jobs/job12345abc/retry");
  });

  it("has no axe violations", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(frames()[0])));
    const { container } = render(<UploadLive api={api} jobId="job12345abc" onFinished={vi.fn()} />);
    await screen.findByText("Saving to PARAKH…");
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
