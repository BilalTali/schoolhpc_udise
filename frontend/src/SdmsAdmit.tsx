import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Upload } from "lucide-react";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";

// New admissions from the filled sheet: upload -> checked here (nothing sent) -> add one first, or all, each after
// confirming. A row added once is never sent again; SDMS's own duplicate / age warnings are left to the person.

interface Row { row: number; name: string; class: string; problems: string[]; added_as: number | null }
interface Plan { file_name: string; checked_at: string; rows: Row[]; ready: number; with_problems: number; already_added: number }
interface Result { row: number; name: string; class: string; student_id: number | null; filled: string[]; error: string | null }
interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; results: Result[]; error: string | null }

export function SdmsAdmit({ api, onAdded }: { api: Api; onAdded: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [first, setFirst] = useState<number | "">("");

  const look = useCallback(async () => {
    try {
      const r = await call<{ plan: Plan | null; job: Job | null }>(api, "GET", "/school/udise/sdms/admit");
      setPlan(r.plan);
      setJob(r.job);
      return r.job;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, [api]);
  useEffect(() => { void look(); }, [look]);
  const running = job?.status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(async () => {
      const j = await look();
      if (j && j.status !== "RUNNING") onAdded();
    }, 2000);
    return () => window.clearTimeout(t);
  }, [running, job, look, onAdded]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/udise/sdms/admit/validate", { method: "POST", body: form }, api.base);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : "The sheet could not be checked.");
      setPlan(body as Plan);
      setJob(null);
      setFirst("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const add = async (rows: number[] | null) => {
    const who = rows ? plan?.rows.find((r) => r.row === rows[0])?.name : `${plan?.ready} new students`;
    if (!window.confirm(`Add ${who} on SDMS now? This creates the student record${rows ? "" : "s"} on SDMS.`)) return;
    setBusy(true);
    setError(null);
    try {
      await call(api, "POST", "/school/udise/sdms/admit", { confirm: true, rows });
      await look();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ready = (plan?.rows || []).filter((r) => !r.problems.length && !r.added_as);
  return (
    <div className="sdms-admit">
      <label className="btn btn-outline sdms-upload">
        <Upload size={15} aria-hidden="true" /> {busy && !running ? "Checking…" : "Upload the filled New admissions sheet"}
        <input type="file" accept=".xlsx" hidden disabled={busy || running}
               onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
      </label>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}

      {plan && !running && (
        <div className="sdms-plan">
          <p><b>{plan.file_name}</b>: <b>{plan.ready}</b> ready to add
            {plan.with_problems > 0 && <>, <b className="sdms-warn">{plan.with_problems}</b> with cells to correct</>}
            {plan.already_added > 0 && <>, {plan.already_added} added already</>}.</p>
          <ul className="sdms-plan-list">
            {plan.rows.map((r) => (
              <li key={r.row}>
                <b>{r.name}</b> · {r.class} · row {r.row}
                {r.added_as ? <span> · <CheckCircle2 size={13} aria-hidden="true" /> added (SDMS ID {r.added_as})</span>
                  : r.problems.length ? <p className="sdms-warn">Correct in the sheet: {r.problems.join("; ")}</p>
                  : <span className="lib-muted"> · ready</span>}
              </li>
            ))}
          </ul>
          {ready.length > 0 && (
            <div className="sdms-actions">
              <select className="form-input" value={first} onChange={(e) => setFirst(e.target.value ? Number(e.target.value) : "")}
                      aria-label="The new student to add first">
                <option value="">Choose one new student to add first…</option>
                {ready.map((r) => <option key={r.row} value={r.row}>{r.name} ({r.class})</option>)}
              </select>
              <button type="button" className="btn btn-outline" disabled={busy || first === ""} onClick={() => add([first as number])}>
                Add this one student
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => add(null)}>Add all {plan.ready} on SDMS</button>
            </div>
          )}
        </div>
      )}

      {job && (
        <div className="sdms-progress" role="status">
          {running && <div><RefreshCw size={14} className="spin" aria-hidden="true" /> <b>Adding on SDMS…</b> {job.done} of {job.total}</div>}
          {job.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
          {job.results.length > 0 && (
            <table className="sdms-table sdms-fit">
              <thead><tr><th>New student</th><th>SDMS ID</th><th>Result</th></tr></thead>
              <tbody>
                {job.results.map((r) => (
                  <tr key={r.row}>
                    <td><b>{r.name}</b><small>{r.class} · row {r.row}</small></td>
                    <td>{r.student_id ?? "—"}</td>
                    <td className={r.error ? "sdms-warn" : ""}>{r.error || <><CheckCircle2 size={14} aria-hidden="true" /> Added; {r.filled.join(", ")} filled</>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
