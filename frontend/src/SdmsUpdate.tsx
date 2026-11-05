import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Upload } from "lucide-react";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";

// Updating SDMS from the filled completion sheet or the All details workbook: upload -> checked here (nothing sent) -> the person saves one
// student first, or all - each after confirming. Every save is read back from SDMS.

interface Change { tab: string; label: string; before: string; after: string; cell?: string }
interface PlanStudent { row: number; sheet?: string; student_id: number; name: string; class: string; changes: Change[]; problems: string[];
  ignored?: string[]; still_missing: string[]; done?: boolean }
interface Plan { file_name: string; checked_at: string; students: PlanStudent[]; not_found: string[]; ready: number; fields: number;
  with_problems: number; already_saved?: number }
interface Result { student_id: number; name: string; class: string; saved: string[]; error: string | null }
interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; results: Result[]; error: string | null }

export function SdmsUpdate({ api, onSaved, full = false }: { api: Api; onSaved: () => void; full?: boolean }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [first, setFirst] = useState<number | "">("");

  const look = useCallback(async () => {
    try {
      const r = await call<{ plan: Plan | null; job: Job | null }>(api, "GET", "/school/udise/sdms/plan");
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
  useEffect(() => {                                          // while saving, look again every 2 s
    if (!running) return;
    const t = window.setTimeout(async () => {
      const j = await look();
      if (j && j.status !== "RUNNING") onSaved();
    }, 2000);
    return () => window.clearTimeout(t);
  }, [running, job, look, onSaved]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/udise/sdms/validate", { method: "POST", body: form }, api.base);
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

  const save = async (only: number[] | null) => {
    const who = only ? plan?.students.find((s) => s.student_id === only[0])?.name : `${plan?.ready} students`;
    if (!window.confirm(`Save the changes for ${who} to SDMS now? This changes the records on SDMS.`)) return;
    setBusy(true);
    setError(null);
    try {
      await call(api, "POST", "/school/udise/sdms/sync", { confirm: true, only });
      await look();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ready = (plan?.students || []).filter((s) => s.changes.length && !s.problems.length && !s.done);
  return (
    <div className="ui-panel">
      <h3 className="lib-section-title">{full ? "Upload the changed student details" : "Upload the filled incomplete forms"}</h3>
      <p className="lib-muted">{full
        ? <>Change any white-headed column on the "All students" sheet (or a class sheet), save the file and upload it here.
            Only the cells you changed are read. Grey-headed columns (class, PEN, name, AADHAAR, scholarships…) are changed on
            SDMS itself.</>
        : <>The sheet has only the students whose SDMS form is incomplete: fill the highlighted (yellow) cells, then upload it here.</>}{" "}
        It is checked against what SDMS holds and nothing is sent until you press Save. AADHAAR and the name as in AADHAAR
        are not changed from here.</p>
      <label className="btn btn-outline sdms-upload">
        <Upload size={15} aria-hidden="true" /> {busy && !running ? "Checking…" : "Upload the filled sheet"}
        <input type="file" accept=".xlsx" hidden disabled={busy || running}
               onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
      </label>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}

      {plan && !running && (
        <div className="sdms-plan">
          <p><b>{plan.file_name}</b>: <b>{plan.ready}</b> student{plan.ready === 1 ? "" : "s"} ready to save ({plan.fields} field{plan.fields === 1 ? "" : "s"})
            {!!plan.already_saved && <>, <b>{plan.already_saved}</b> already saved on SDMS (not sent again)</>}
            {plan.with_problems > 0 && <>, <b className="sdms-warn">{plan.with_problems}</b> with cells to correct first</>}.</p>
          {plan.not_found.length > 0 && (
            <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{plan.not_found.join("; ")}</div></div>
          )}
          <ul className="sdms-plan-list">
            {plan.students.map((s) => (
              <li key={s.student_id}>
                <details open={plan.students.length <= 5}>
                  <summary>{s.done && <CheckCircle2 size={14} aria-hidden="true" color="#046A38" />} <b>{s.name}</b>{s.done && " (saved)"} · {s.class} · {s.sheet ? `'${s.sheet}' ` : ""}row {s.row} · {s.changes.length} change{s.changes.length === 1 ? "" : "s"}
                    {s.problems.length > 0 && <span className="sdms-warn"> · {s.problems.length} to correct</span>}</summary>
                  {s.changes.length > 0 && (
                    <table className="sdms-table sdms-fit">
                      <thead><tr><th>Tab</th><th>Field</th><th>Now on SDMS</th><th>After saving</th></tr></thead>
                      <tbody>{s.changes.map((c) => <tr key={c.label}><td>{c.tab}</td><td>{c.label}</td><td>{c.before || "—"}</td><td><b>{c.after}</b></td></tr>)}</tbody>
                    </table>
                  )}
                  {s.problems.length > 0 && <p className="sdms-warn">Correct in the sheet: {s.problems.join("; ")}</p>}
                  {!!s.ignored?.length && <p className="lib-muted">Changed in the file but not sent (change on SDMS itself): {s.ignored.join("; ")}</p>}
                  {s.still_missing.length > 0 && <p className="lib-muted">Still missing after this: {s.still_missing.join("; ")}</p>}
                </details>
              </li>
            ))}
          </ul>
          {ready.length > 0 && (
            <div className="sdms-actions">
              <select className="form-input" value={first} onChange={(e) => setFirst(e.target.value ? Number(e.target.value) : "")}
                      aria-label="The student to save first">
                <option value="">Choose one student to save first…</option>
                {ready.map((s) => <option key={s.student_id} value={s.student_id}>{s.name} ({s.class})</option>)}
              </select>
              <button type="button" className="btn btn-outline" disabled={busy || first === ""} onClick={() => save([first as number])}>
                Save this one student
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => save(null)}>
                Save all {plan.ready} to SDMS
              </button>
            </div>
          )}
        </div>
      )}

      {job && (
        <div className="sdms-progress" role="status">
          {running && <div><RefreshCw size={14} className="spin" aria-hidden="true" /> <b>Saving to SDMS…</b> {job.done} of {job.total}</div>}
          {running && <div className="sdms-bar"><span style={{ width: `${job.total ? Math.round((job.done / job.total) * 100) : 5}%` }} /></div>}
          {job.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
          {job.results.length > 0 && (<>
            <p><b>{job.results.filter((r) => !r.error).length}</b> saved and confirmed on SDMS
              {job.results.some((r) => r.error) && <>, <b className="sdms-warn">{job.results.filter((r) => r.error).length}</b> not saved (listed first)</>}.</p>
            <table className="sdms-table sdms-results">
              <colgroup><col style={{ width: "28%" }} /><col style={{ width: "20%" }} /><col /></colgroup>
              <thead><tr><th>Student</th><th>Saved</th><th>Result</th></tr></thead>
              <tbody>
                {[...job.results].sort((x, y) => Number(!x.error) - Number(!y.error)).map((r) => (
                  <tr key={r.student_id}>
                    <td><b>{r.name}</b><small>{r.class}</small></td>
                    <td>{r.saved.join(", ") || "—"}</td>
                    <td className={r.error ? "sdms-warn" : ""}>{r.error || <><CheckCircle2 size={14} aria-hidden="true" /> Saved and confirmed on SDMS</>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>)}
        </div>
      )}
    </div>
  );
}
