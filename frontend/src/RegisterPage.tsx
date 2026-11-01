import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";

// School Register (docs/school_register_plan.md): the school fetches every student from PARAKH with its own login
// (read only); teachers then get their students from here. Shows each stage's students, their PARAKH identity and
// teachers, and who has no teacher yet.

interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; step: string; done: number; total: number; error: string | null;
  notes: string[]; stages: Record<string, { added: number; updated: number; missing: number; listed: number }>; finished_at?: string }
interface Student { id: string; stage: string; student_id: string; student_name: string; hpc_login_id: string | null;
  apaar_id: string | null; grade: string | null; section: string | null; gender: string | null; dob: string | null;
  admission_number: string | null; hpc_status: string | null; teachers: string[]; missing_on_parakh: boolean }
interface Register { students: Student[]; summary: Record<string, { students: number; assigned: number; unassigned: number; missing_on_parakh: number }> }

const STAGES = ["Foundational", "Preparatory", "Middle"];

export function RegisterPage({ api }: { api: Api }) {
  const [reg, setReg] = useState<Register | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState("all");
  const [only, setOnly] = useState<"all" | "unassigned" | "missing">("all");
  const [find, setFind] = useState("");
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([call<Register>(api, "GET", "/school/register"),
                                        call<{ job: Job | null }>(api, "GET", "/school/register/fetch")]);
      setReg(r);
      setJob(p.job);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  const running = job?.status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    timer.current = window.setTimeout(() => { void load(); }, 1500);
    return () => window.clearTimeout(timer.current);
  }, [running, job, load]);

  const fetchAll = async () => {
    setError(null);
    try {
      await call(api, "POST", "/school/register/fetch", {});
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const rows = useMemo(() => {
    const q = find.trim().toLowerCase();
    return (reg?.students || []).filter((s) => (stage === "all" || s.stage === stage)
      && (only === "all" || (only === "unassigned" ? !s.teachers.length : s.missing_on_parakh))
      && (!q || `${s.student_name} ${s.student_id} ${s.apaar_id || ""} ${s.admission_number || ""}`.toLowerCase().includes(q)));
  }, [reg, stage, only, find]);

  return (
    <div className="sdms">
      <div className="ui-panel">
        <div className="sdms-head">
          <div>
            <h2 className="sdms-title">School Register</h2>
            <p className="lib-muted">Every student of the school as PARAKH has them - with a teacher or not. Read with the
              school's PARAKH login (nothing is changed on PARAKH). Teachers get their students from here.</p>
          </div>
          <div className="sdms-actions">
            <button type="button" className="btn btn-primary" onClick={fetchAll} disabled={running}>
              <RefreshCw size={15} aria-hidden="true" className={running ? "spin" : ""} /> {reg?.students.length ? "Fetch again from PARAKH" : "Fetch all students from PARAKH"}
            </button>
          </div>
        </div>
        {running && job && (
          <div className="sdms-progress" role="status">
            <div><b>{job.step}</b>{job.total ? ` · ${job.done} of ${job.total} students` : ""}</div>
            <div className="sdms-bar"><span style={{ width: `${job.total ? Math.round((job.done / job.total) * 100) : 5}%` }} /></div>
          </div>
        )}
        {job?.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
        {job?.status === "COMPLETED" && (
          <p className="lib-muted" role="status">Last fetch: {Object.entries(job.stages).map(([st, c]) =>
            `${st} ${c.listed} (${c.added} new${c.missing ? `, ${c.missing} no longer on PARAKH` : ""})`).join(" · ")}
            {job.notes.length > 0 && <> · <span className="sdms-warn">{job.notes.join(" ")}</span></>}</p>
        )}
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      </div>

      {reg && (
        <div className="ui-panel">
          <table className="sdms-table sdms-fit">
            <thead><tr><th>Stage</th><th>Students</th><th>With a teacher</th><th>No teacher</th><th>No longer on PARAKH</th></tr></thead>
            <tbody>{STAGES.filter((s) => reg.summary[s]).map((s) => (
              <tr key={s}><td>{s}</td><td>{reg.summary[s].students}</td><td>{reg.summary[s].assigned}</td>
                <td className={reg.summary[s].unassigned ? "sdms-warn" : ""}>{reg.summary[s].unassigned}</td>
                <td>{reg.summary[s].missing_on_parakh}</td></tr>))}
              {!Object.keys(reg.summary).length && <tr><td colSpan={5} className="lib-muted">Nothing fetched yet.</td></tr>}
            </tbody>
          </table>
          <div className="sdms-actions" style={{ marginTop: "0.75rem" }}>
            <select className="form-select" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
              <option value="all">Every stage</option>{STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="form-select" value={only} onChange={(e) => setOnly(e.target.value as typeof only)} aria-label="Show">
              <option value="all">All students</option><option value="unassigned">No teacher</option>
              <option value="missing">No longer on PARAKH</option>
            </select>
            <input className="form-input" placeholder="Find a name, PARAKH id, APAAR, admission no." value={find}
                   onChange={(e) => setFind(e.target.value)} aria-label="Find" />
          </div>
          <div className="sdms-scroll"><table className="sdms-table sdms-fit">
            <thead><tr><th>Stage</th><th>Class</th><th>Name (as on PARAKH)</th><th>PARAKH id</th><th>APAAR</th><th>Admission no.</th>
              <th>DOB</th><th>Teacher</th><th>HPC on PARAKH</th></tr></thead>
            <tbody>{rows.map((s) => (
              <tr key={s.id} className={s.missing_on_parakh ? "lib-muted" : ""}>
                <td>{s.stage}</td><td>{s.grade} {s.section}</td><td><b>{s.student_name}</b></td><td>{s.student_id}</td>
                <td>{s.apaar_id || "—"}</td><td>{s.admission_number || "—"}</td><td>{s.dob || "—"}</td>
                <td className={s.teachers.length ? "" : "sdms-warn"}>{s.teachers.join(", ") || "No teacher"}</td>
                <td>{s.missing_on_parakh ? "No longer listed" : s.hpc_status || "—"}</td></tr>))}
            </tbody>
          </table></div>
          <p className="lib-muted">{rows.length} of {reg.students.length} shown.</p>
        </div>
      )}
    </div>
  );
}
