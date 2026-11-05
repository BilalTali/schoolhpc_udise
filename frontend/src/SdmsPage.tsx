import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ClipboardCheck, Download, RefreshCw, UserPlus, Users } from "lucide-react";
import { CardHub } from "./CardHub";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";
import { saveBlob } from "./downloadSheet";
import { SdmsUpdate } from "./SdmsUpdate";
import { SdmsAdmit } from "./SdmsAdmit";

// SDMS (UDISE+ Student module), current session: fetch every student of every class (read only), see them by class,
// and download all their details as Excel to check what needs updating.

interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; step: string; done: number; total: number; error: string | null; finished_at: string | null }
interface Progress { job: Job | null; saved: { fetched_at: string; session: string; students: number; problems: number } | null }
interface ClassRow { class_id: number; class: string; boys: number; girls: number; trans: number; total: number; incomplete: number }
interface StudentRow {
  student_id: number; pen: string; name: string; class_id: number; class: string; section: string; gender: string; dob: string;
  father: string; mother: string; mobile: string; admission_no: string; aadhaar_status: string; form: string; problems: string[];
  details: { section: string; fields: { label: string; value: string | number | null }[] }[];
}
interface View { fetched_at: string; session: string; school: { schoolName?: string; udiseSchCode?: string }; classes: ClassRow[]; students: StudentRow[] }

const PAGE_SIZE = 20;
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");

export function SdmsPage({ api }: { api: Api }) {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cls, setCls] = useState<string>("all");
  const [find, setFind] = useState("");
  const [open, setOpen] = useState<StudentRow | null>(null);           // the student whose form is shown
  const [page, setPage] = useState(0);                                  // the student table, PAGE_SIZE at a time
  const timer = useRef<number | undefined>(undefined);

  const [todo, setTodo] = useState<{ students: number; to_complete: number; fields: [string, number][] } | null>(null);
  const loadView = useCallback(async () => {
    try {
      setView(await call<View>(api, "GET", "/school/udise/sdms/students"));
      setTodo(await call<{ students: number; to_complete: number; fields: [string, number][] }>(api, "GET", "/school/udise/sdms/completion"));
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) setError((e as Error).message);
    }
  }, [api]);

  const poll = useCallback(async () => {
    try {
      const p = await call<Progress>(api, "GET", "/school/udise/sdms/fetch");
      setProgress(p);
      if (p.job?.status !== "RUNNING" && (p.job?.status === "COMPLETED" || p.saved)) loadView();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, loadView]);

  useEffect(() => { void poll(); }, [poll]);
  const running = progress?.job?.status === "RUNNING";
  useEffect(() => {                                            // while a fetch runs, ask again every 1.5 s
    if (!running) return;
    timer.current = window.setTimeout(() => { void poll(); }, 1500);
    return () => window.clearTimeout(timer.current);
  }, [running, progress, poll]);

  const fetchAll = async () => {
    setError(null);
    try {
      const r = await call<{ started: boolean; error?: string }>(api, "POST", "/school/udise/sdms/fetch");
      if (!r.started) setError(r.error || "The fetch could not start.");
      poll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const download = async (sheet: "students" | "completion" | "new-admissions" = "students") => {
    const res = await apiFetch(`/school/udise/sdms/${sheet}.xlsx`, {}, api.base);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(`The Excel file could not be made${body?.detail ? `: ${body.detail}` : ` (error ${res.status})`}.`);
      return;
    }
    saveBlob(await res.blob(), `SDMS_${sheet === "completion" ? "to_complete" : sheet === "new-admissions" ? "new_admissions" : "students"}_${view?.session || ""}.xlsx`);
  };

  const job = progress?.job;
  const rows = useMemo(() => {
    const q = find.trim().toLowerCase();
    return (view?.students || []).filter((s) => (cls === "all" || String(s.class_id) === cls)
      && (!q || `${s.name} ${s.pen} ${s.father} ${s.mother} ${s.admission_no}`.toLowerCase().includes(q)));
  }, [view, cls, find]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const at = Math.min(page, pages - 1);
  const shown = rows.slice(at * PAGE_SIZE, at * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="sdms">
      <div className="ui-panel">
        <div className="sdms-head">
          <div>
            <h2 className="sdms-title">Student module (SDMS)</h2>
            <p className="lib-muted">
              {view ? <>Session <b>{view.session}</b> · {view.school.schoolName} · fetched {when(view.fetched_at)}</>
                    : "Current session. Fetch reads every student of every class from SDMS; nothing is changed there."}
            </p>
          </div>
          <div className="sdms-actions">
            <button type="button" className="btn btn-primary" onClick={fetchAll} disabled={running}>
              <RefreshCw size={15} aria-hidden="true" className={running ? "spin" : ""} /> {view ? "Fetch again" : "Fetch all students"}
            </button>
          </div>
        </div>

        {running && job && (
          <div className="sdms-progress" role="status">
            <div><b>{job.step}</b>{job.total ? ` · ${job.done} of ${job.total} students` : ""}</div>
            <div className="sdms-bar"><span style={{ width: `${job.total ? Math.round((job.done / job.total) * 100) : 5}%` }} /></div>
            <small className="lib-muted">About 1 second per student, gentle on UDISE+. You can leave this page; it carries on.</small>
          </div>
        )}
        {job?.status === "FAILED" && job.error && (
          <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>
        )}
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
        {job?.status === "COMPLETED" && progress?.saved && (
          <p className="sdms-done"><CheckCircle2 size={16} aria-hidden="true" /> {progress.saved.students} students fetched
            {progress.saved.problems ? ` · ${progress.saved.problems} with a part SDMS did not send (see the Problems column)` : ""}.</p>
        )}
      </div>

      {view && (
        <CardHub label="Students (SDMS)" cards={[
          { key: "students", title: "All students", icon: Users, stat: view.students.length, statLabel: `in ${view.classes.length} classes`, tone: "info",
            about: "Every class and every student as SDMS holds them; open any student's full form.", body: () => (<>
          <div className="ui-panel">
            <h3 className="lib-section-title">Classes</h3>
            <div className="sdms-scroll">
              <table className="sdms-table sdms-fit">
                <thead><tr><th>Class</th><th className="sdms-mid">Boys</th><th className="sdms-mid">Girls</th><th className="sdms-wide">Transgender</th><th>Total</th><th>Incomplete</th><th><span className="sr-only">Students</span></th></tr></thead>
                <tbody>
                  {view.classes.map((c) => (
                    <tr key={c.class_id}>
                      <td>{c.class}</td><td className="sdms-mid">{c.boys}</td><td className="sdms-mid">{c.girls}</td><td className="sdms-wide">{c.trans}</td><td><b>{c.total}</b></td>
                      <td className={c.incomplete ? "sdms-warn" : ""}>{c.incomplete}</td>
                      <td><button type="button" className="btn btn-outline btn-sm" onClick={() => { setCls(String(c.class_id)); setPage(0); }}>View students</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="ui-panel">
            <div className="sdms-filters">
              <label>Class
                <select className="form-input" value={cls} onChange={(e) => { setCls(e.target.value); setPage(0); }}>
                  <option value="all">All classes</option>
                  {view.classes.map((c) => <option key={c.class_id} value={String(c.class_id)}>{c.class}</option>)}
                </select>
              </label>
              <label className="sdms-find">Find
                <input type="search" className="form-input" value={find} onChange={(e) => { setFind(e.target.value); setPage(0); }}
                       placeholder="Name, PEN, parent or admission number" />
              </label>
              <span className="lib-muted">{rows.length} student{rows.length === 1 ? "" : "s"}</span>
            </div>
            <div className="sdms-scroll sdms-scroll-tall">
              <table className="sdms-table sdms-fit">
                <thead>
                  <tr><th>Student</th><th>Class</th><th className="sdms-wide">Parents</th><th className="sdms-mid">Mobile</th>
                    <th className="sdms-mid">Admission no.</th><th>Form</th><th><span className="sr-only">Open</span></th></tr>
                </thead>
                <tbody>
                  {shown.map((s) => (
                    <tr key={s.student_id}>
                      <td><b>{s.name}</b><small>PEN {s.pen} · {s.gender} · {s.dob}</small></td>
                      <td>{s.class}{s.section ? ` ${s.section}` : ""}</td>
                      <td className="sdms-wide">{s.father}<small>{s.mother}</small></td>
                      <td className="sdms-mid">{s.mobile}</td>
                      <td className="sdms-mid">{s.admission_no}</td>
                      <td><span className={`sdms-chip ${s.form === "Completed" ? "ok" : "todo"}`}>{s.form}</span>
                        {s.problems.length > 0 && <small className="sdms-warn">{s.problems.join("; ")}</small>}</td>
                      <td><button type="button" className="btn btn-outline btn-sm" onClick={() => setOpen(s)}>Open</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <nav className="sdms-pager" aria-label="Student pages">
                <button type="button" className="btn btn-outline btn-sm" onClick={() => setPage(at - 1)} disabled={at === 0}>Previous</button>
                <span>Page {at + 1} of {pages} · students {at * PAGE_SIZE + 1}–{Math.min(rows.length, (at + 1) * PAGE_SIZE)} of {rows.length}</span>
                <button type="button" className="btn btn-outline btn-sm" onClick={() => setPage(at + 1)} disabled={at >= pages - 1}>Next</button>
              </nav>
            )}
          </div>
            </>) },
          { key: "complete", title: "To complete", icon: ClipboardCheck, stat: todo ? todo.to_complete : "…", statLabel: "students",
            tone: todo?.to_complete ? "warn" : "good",
            about: "Only the students whose form is incomplete, with the fields still missing: download, fill, upload, save to SDMS.", body: () => (<>
        <div className="ui-panel">
          <button type="button" className="btn btn-outline" onClick={() => download("completion")} disabled={running}>
            <Download size={15} aria-hidden="true" /> Download incomplete forms only
          </button>
          {!todo ? <p className="lib-muted">Counting…</p> : todo.to_complete === 0 ? (
            <p className="sdms-done"><CheckCircle2 size={16} aria-hidden="true" /> Every required field of every student is filled.</p>
          ) : (
            <>
              <p><b>{todo.to_complete} of {todo.students}</b> students have required fields that are empty or not accepted by SDMS.
                The completion sheet lists them by class, with the cells to fill highlighted.</p>
              <ul className="sdms-todo">
                {todo.fields.map(([field, n]) => <li key={field}><b>{n}</b> {field}</li>)}
              </ul>
            </>
          )}
        </div>
              <SdmsUpdate api={api} onSaved={() => { void loadView(); }} />
            </>) },
          { key: "admit", title: "New admissions", icon: UserPlus, stat: "KG–I", statLabel: "for now",
            about: "Add new students from one sheet: checked first, added on SDMS only when you press Add.", body: () => (
        <div className="ui-panel">
          <p className="lib-muted">SDMS's "Add Student" form for this session asks for class, section, name, gender, date of birth,
            mother's and father's names, Aadhaar and the name as in it, admission date, mobile and CWSN. The rest of the student
            form must be filled before the student counts as complete. This sheet has all of it, one row per new student, with
            SDMS's own choices in drop-downs (columns marked * are required). Fill it, upload it below: it is checked first,
            and nothing is added on SDMS until you press Add. KG classes and Class I for now.</p>
          <button type="button" className="btn btn-outline" onClick={() => download("new-admissions")}>
            <Download size={15} aria-hidden="true" /> New admissions sheet
          </button>
          <SdmsAdmit api={api} onAdded={() => { void loadView(); }} />
        </div>
            ) },
          { key: "excel", title: "All details in Excel", icon: Download, stat: view.session, statLabel: "session",
            about: "Every student's full form, laid out like SDMS's tabs: change it in Excel and upload it back.", body: () => (<>
        <div className="ui-panel">
          <p className="lib-muted">One row per student, the columns in SDMS's own order. Drop-downs give SDMS's choices.</p>
          <button type="button" className="btn btn-outline" onClick={() => download()} disabled={running}>
            <Download size={15} aria-hidden="true" /> Download all details (Excel)
          </button>
        </div>
              <SdmsUpdate api={api} full onSaved={() => { void loadView(); }} />
            </>) },
        ]} />
      )}
      {open && <StudentForm student={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** One student's SDMS form, tab by tab, with the questions and answers as SDMS shows them. */
function StudentForm({ student, onClose }: { student: StudentRow; onClose: () => void }) {
  const [tab, setTab] = useState(1);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  const sections = student.details;
  return (
    <div className="sdms-overlay" role="presentation" onClick={onClose}>
      <section className="sdms-form" role="dialog" aria-modal="true" aria-labelledby="sdms-form-title" onClick={(e) => e.stopPropagation()}>
        <header className="sdms-form-head">
          <div>
            <h3 id="sdms-form-title">{student.name}</h3>
            <p className="lib-muted">Class {student.class} {student.section} · PEN {student.pen} · {student.form}</p>
          </div>
          <button type="button" className="btn btn-outline" onClick={onClose} autoFocus>Close</button>
        </header>
        <div className="sdms-tabs" role="tablist">
          {sections.map((sec, i) => i > 0 && (
            <button key={sec.section} type="button" role="tab" aria-selected={tab === i}
                    className={`sdms-tab ${tab === i ? "on" : ""}`} onClick={() => setTab(i)}>{sec.section}</button>
          ))}
        </div>
        <dl className="sdms-fields">
          {sections[tab]?.fields.map((f) => (
            <div key={f.label} className="sdms-field">
              <dt>{f.label}</dt>
              <dd>{f.value === "" || f.value === null ? <span className="lib-muted">—</span> : String(f.value)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
