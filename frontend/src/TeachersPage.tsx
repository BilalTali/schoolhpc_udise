import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileDown, RefreshCw, Upload } from "lucide-react";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";
import { downloadSheet } from "./downloadSheet";

// UDISE+ Teacher module: read every staff member's forms, see exactly what is still needed (and where in the Excel),
// download the Excel (one row per person, a sheet for new staff), upload it back -> checked here -> save after
// confirming. Certifying stays on the UDISE+ website.

interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; step: string; done: number; total: number; error: string | null }
interface Person { name: string; national_code: string; complete_on_udise: boolean; missing: string[]; errors: Record<string, string>; row: number }
interface Group { type: number; label: string; staff: number; complete: number; people: Person[] }
interface Needed { type: string; staff: string; form: string; field: string; sheet: string; row: number; column: string; allowed: string }
interface Updated { at: string; staff: string; form: string; field: string; before: string | null; after: string | null; result: string }
interface Status { read_at: string; groups: Group[]; needed: Needed[]; updated: Updated[]; save_enabled: boolean }
interface Change { form: string; key: string; label: string; cell: string; old: string | null; new: string | null; warning: string }
interface PlanPerson { staff_id: number | null; name: string; sheet: string; row: number; new: boolean; changes: Change[]; problems: string[] }
interface Plan { file_name: string; checked_at: string; people: PlanPerson[]; problems: number; changes: number; new_staff: number;
  save_enabled: boolean; results: { at: string; items: { name: string; form: string; status: string; message: string }[] } | null }
interface Overview { job: Job | null; saved: { read_at: string; staff: number } | null; status: Status | null; plan: Plan | null }

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");

export function TeachersPage({ api }: { api: Api }) {
  const [data, setData] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const r = await call<Overview>(api, "GET", "/school/udise/teachers");
      setData(r);
      setPlan(r.plan);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  const running = data?.job?.status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    timer.current = window.setTimeout(() => { void load(); }, 1500);
    return () => window.clearTimeout(timer.current);
  }, [running, data, load]);

  const read = async () => {
    setError(null);
    try {
      await call(api, "POST", "/school/udise/teachers/read");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const upload = async (file: File) => {
    setBusy("checking");
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/udise/teachers/validate", { method: "POST", body: form }, api.base);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : "The workbook could not be checked.");
      setPlan(body as Plan);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const save = async () => {
    if (!plan || !window.confirm(`Save ${plan.changes} change${plan.changes === 1 ? "" : "s"} to UDISE+ now? This changes the staff records on UDISE+.`)) return;
    setBusy("saving");
    setError(null);
    try {
      await call(api, "POST", "/school/udise/teachers/save", { confirm: true });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const st = data?.status;
  const job = data?.job;
  return (
    <div className="sdms">
      <div className="ui-panel">
        <div className="sdms-head">
          <div>
            <h2 className="sdms-title">Teacher module (staff)</h2>
            <p className="lib-muted">{st ? <>{st.groups.reduce((n, g) => n + g.staff, 0)} staff · read from UDISE+ {when(st.read_at)}</>
              : "Read every staff member's forms from UDISE+ (nothing is changed there)."}</p>
          </div>
          <div className="sdms-actions">
            <button type="button" className="btn btn-primary" onClick={read} disabled={running || !!busy}>
              <RefreshCw size={15} aria-hidden="true" className={running ? "spin" : ""} /> {st ? "Read again" : "Read staff from UDISE+"}
            </button>
            {st && <>
              <button type="button" className="btn btn-outline" disabled={!!busy}
                      onClick={async () => setError(await downloadSheet(api, "/school/udise/teachers.xlsx", "UDISE_Teachers.xlsx"))}>
                <Download size={15} aria-hidden="true" /> Download Excel
              </button>
              <label className="btn btn-outline sdms-upload">
                <Upload size={15} aria-hidden="true" /> {busy === "checking" ? "Checking…" : "Upload filled Excel"}
                <input type="file" accept=".xlsx" hidden disabled={!!busy}
                       onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
              </label>
              <button type="button" className="btn btn-outline" disabled={!!busy}
                      onClick={async () => setError(await downloadSheet(api, "/school/udise/reports/teachers.pdf", "UDISE_Teachers_status.pdf"))}>
                <FileDown size={15} aria-hidden="true" /> Status report (PDF)
              </button>
            </>}
          </div>
        </div>
        {running && job && (
          <div className="sdms-progress" role="status">
            <div><b>{job.step}</b>{job.total ? ` · ${job.done} of ${job.total} staff` : ""}</div>
            <div className="sdms-bar"><span style={{ width: `${job.total ? Math.round((job.done / job.total) * 100) : 5}%` }} /></div>
          </div>
        )}
        {job?.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      </div>

      {plan && (
        <div className="ui-panel">
          <h3 className="lib-section-title">Checked workbook</h3>
          <p><b>{plan.file_name}</b>, checked {when(plan.checked_at)}: <b>{plan.changes}</b> change{plan.changes === 1 ? "" : "s"},{" "}
            <b>{plan.new_staff}</b> new staff{plan.problems > 0 && <>, <b className="sdms-warn">{plan.problems}</b> cell{plan.problems === 1 ? "" : "s"} to correct</>}.</p>
          <ul className="sdms-plan-list">
            {plan.people.map((p, i) => (
              <li key={i}>
                <details open={plan.people.length <= 4 || p.problems.length > 0}>
                  <summary><b>{p.name}</b> · {p.new ? "new staff" : p.sheet} · row {p.row} · {p.changes.length} change{p.changes.length === 1 ? "" : "s"}
                    {p.problems.length > 0 && <span className="sdms-warn"> · {p.problems.length} to correct</span>}</summary>
                  {p.problems.length > 0 && <ul className="sdms-warn">{p.problems.map((m, j) => <li key={j}>{m}</li>)}</ul>}
                  {p.changes.length > 0 && (
                    <table className="sdms-table sdms-fit">
                      <thead><tr><th>Form</th><th>Field</th><th>Cell</th><th>Now on UDISE+</th><th>After saving</th></tr></thead>
                      <tbody>{p.changes.map((c, j) => (
                        <tr key={j}><td>Form {c.form}</td><td>{c.label}{c.warning && <small className="sdms-warn"> {c.warning}</small>}</td>
                          <td>{c.cell || "—"}</td><td>{c.old ?? "—"}</td><td><b>{c.new ?? "—"}</b></td></tr>))}
                      </tbody>
                    </table>)}
                </details>
              </li>))}
          </ul>
          {plan.save_enabled
            ? <button type="button" className="btn btn-primary" disabled={!!busy || plan.changes === 0} onClick={save}>
                {busy === "saving" ? "Saving to UDISE+…" : "Save changes to UDISE+"}</button>
            : <p className="lib-muted">Saving staff to UDISE+ is switched on after the app has been checked against this school's real
                staff data. Until then nothing is sent: use the list above to update on the UDISE+ website.</p>}
          {plan.results && (
            <table className="sdms-table sdms-fit" role="status">
              <thead><tr><th>Staff</th><th>Form</th><th>Result</th></tr></thead>
              <tbody>{plan.results.items.map((r, i) => (
                <tr key={i}><td>{r.name}</td><td>{r.form}</td><td className={r.status === "saved" ? "" : "sdms-warn"}>
                  {r.status === "saved" && <CheckCircle2 size={14} aria-hidden="true" />} {r.status}{r.message && ` · ${r.message}`}</td></tr>))}
              </tbody>
            </table>)}
        </div>
      )}

      {st && (
        <div className="ui-panel">
          <h3 className="lib-section-title">Where each staff member stands</h3>
          {st.groups.map((g) => (
            <details key={g.type} open={g.staff > 0 && g.staff <= 25}>
              <summary><b>{g.label}</b>: {g.staff} · {g.complete} complete</summary>
              {g.staff > 0 && (
                <table className="sdms-table sdms-fit">
                  <thead><tr><th>Name</th><th>National code</th><th>Forms complete on UDISE+</th><th>Still needed</th><th>Excel row</th></tr></thead>
                  <tbody>{g.people.map((p, i) => (
                    <tr key={i}><td><b>{p.name}</b></td><td>{p.national_code || "—"}</td><td>{p.complete_on_udise ? "Yes" : "No"}</td>
                      <td className={p.missing.length ? "sdms-warn" : ""}>{p.missing.length ? p.missing.join("; ") : "—"}
                        {Object.keys(p.errors).length > 0 && <small> · could not read: {Object.values(p.errors).join("; ")}</small>}</td>
                      <td>{p.row}</td></tr>))}
                  </tbody>
                </table>)}
            </details>))}
          <details open={st.needed.length > 0 && st.needed.length <= 40}>
            <summary><b>Still needed: {st.needed.length}</b> field{st.needed.length === 1 ? "" : "s"}, with their cell in the Excel</summary>
            <div className="sdms-scroll"><table className="sdms-table sdms-fit">
              <thead><tr><th>Name</th><th>Form</th><th>Field</th><th>In the workbook</th><th>Allowed</th></tr></thead>
              <tbody>{st.needed.map((n, i) => (
                <tr key={i}><td>{n.staff}</td><td>{n.form}</td><td>{n.field}</td><td>"{n.sheet}" {n.column}{n.row}</td><td>{n.allowed}</td></tr>))}
              </tbody></table></div>
          </details>
          <details>
            <summary><b>Updated from the app: {st.updated.length}</b></summary>
            {st.updated.length === 0 ? <p className="lib-muted">Nothing has been saved from the app yet.</p> : (
              <table className="sdms-table sdms-fit">
                <thead><tr><th>When</th><th>Name</th><th>Form</th><th>Field</th><th>Before</th><th>After</th><th>Result</th></tr></thead>
                <tbody>{[...st.updated].reverse().map((u, i) => (
                  <tr key={i}><td>{when(u.at)}</td><td>{u.staff}</td><td>{u.form}</td><td>{u.field}</td><td>{u.before ?? "—"}</td>
                    <td><b>{u.after ?? "—"}</b></td><td>{u.result}</td></tr>))}
                </tbody></table>)}
          </details>
        </div>
      )}
    </div>
  );
}
