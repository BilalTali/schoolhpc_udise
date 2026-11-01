import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Download, RefreshCw, Upload } from "lucide-react";
import { apiFetch, call } from "./api";
import { downloadSheet } from "./downloadSheet";
import type { Api } from "./api";

// School Register (docs/school_register_plan.md): the school fetches every student from PARAKH with its own login
// (read only); teachers then get their students from here. Shows each stage's students, their PARAKH identity and
// teachers, and who has no teacher yet.

interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; step: string; done: number; total: number; error: string | null;
  notes: string[]; stages: Record<string, { added: number; updated: number; missing: number; listed: number }>; finished_at?: string }
interface Student { id: string; stage: string; student_id: string; student_name: string; hpc_login_id: string | null;
  apaar_id: string | null; grade: string | null; section: string | null; gender: string | null; dob: string | null;
  admission_number: string | null; hpc_status: string | null; teachers: string[]; missing_on_parakh: boolean;
  card: { status: string; detail: string; at: string; teacher: string } | null;
  entered: { present: number; working: number; percent: number | null; months: number; father: string | null;
             mother: string | null; card_name: string | null; marks: number; marks_of: number } | null }
interface Register { students: Student[]; summary: Record<string, { students: number; assigned: number; unassigned: number; missing_on_parakh: number }>;
  card_status?: Record<string, Record<string, number>> }
const CARD_STATUSES = ["Verified on PARAKH", "Submitted", "Submission failed", "Requires correction", "Teacher work in progress",
  "Assigned to teacher", "Fetched", "No longer on PARAKH"];
const CARD_TONE: Record<string, string> = { "Verified on PARAKH": "", "Submission failed": "sdms-warn", "Requires correction": "sdms-warn",
  "Fetched": "sdms-warn" };

const STAGES = ["Foundational", "Preparatory", "Middle"];
const PAGE_SIZE = 25;

export function RegisterPage({ api }: { api: Api }) {
  const [reg, setReg] = useState<Register | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState("all");
  const [only, setOnly] = useState<"all" | "unassigned" | "missing">("all");
  const [find, setFind] = useState("");
  const [cardStatus, setCardStatus] = useState("all");
  const [page, setPage] = useState(0);
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
      && (cardStatus === "all" || s.card?.status === cardStatus)
      && (!q || `${s.student_name} ${s.student_id} ${s.apaar_id || ""} ${s.admission_number || ""}`.toLowerCase().includes(q)));
  }, [reg, stage, only, find, cardStatus]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const at = Math.min(page, pages - 1);

  return (
    <div className="sdms">
      <div className="ui-panel">
        <div className="sdms-head">
          <div>
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

      {reg && reg.students.length > 0 && <SchoolDashboard api={api} />}
      {reg && reg.students.length > 0 && <SchoolSettings api={api} />}
      {reg && reg.students.length > 0 && <SchoolData api={api} onSaved={() => { void load(); }} />}

      {reg && (
        <div className="ui-panel">
          <table className="sdms-table">
            <thead><tr><th>Stage</th><th>Students</th><th>With a teacher</th><th>No teacher</th><th>Gone from PARAKH</th></tr></thead>
            <tbody>{STAGES.filter((s) => reg.summary[s]).map((s) => (
              <tr key={s}><td>{s}</td><td>{reg.summary[s].students}</td><td>{reg.summary[s].assigned}</td>
                <td className={reg.summary[s].unassigned ? "sdms-warn" : ""}>{reg.summary[s].unassigned}</td>
                <td>{reg.summary[s].missing_on_parakh}</td></tr>))}
              {!Object.keys(reg.summary).length && <tr><td colSpan={5} className="lib-muted">Nothing fetched yet.</td></tr>}
            </tbody>
          </table>
          {reg.card_status && Object.keys(reg.card_status).length > 0 && (
            <div className="sdms-scroll"><table className="sdms-table" style={{ marginTop: "0.75rem" }}>
              <thead><tr><th>Cards on PARAKH</th>{CARD_STATUSES.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{STAGES.filter((st) => reg.card_status![st]).map((st) => (
                <tr key={st}><td>{st}</td>{CARD_STATUSES.map((c) => (
                  <td key={c}>{reg.card_status![st][c] ? (
                    <button type="button" className="portal-link-btn" onClick={() => { setStage(st); setCardStatus(c); setPage(0); }}>
                      {reg.card_status![st][c]}</button>) : 0}</td>))}</tr>))}
              </tbody></table></div>)}
          <div className="reg-toolbar" style={{ marginTop: "0.75rem" }}>
            <label className="reg-field"><span>Stage</span>
              <select className="reg-box" value={stage} onChange={(e) => { setStage(e.target.value); setPage(0); }}>
                <option value="all">Every stage</option>{STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select></label>
            <label className="reg-field"><span>Show</span>
              <select className="reg-box" value={only} onChange={(e) => { setOnly(e.target.value as typeof only); setPage(0); }}>
                <option value="all">All students</option><option value="unassigned">No teacher</option>
                <option value="missing">No longer on PARAKH</option>
              </select></label>
            <label className="reg-field"><span>Card on PARAKH</span>
              <select className="reg-box" value={cardStatus} onChange={(e) => { setCardStatus(e.target.value); setPage(0); }}>
                <option value="all">Any</option>{CARD_STATUSES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></label>
            <label className="reg-field" style={{ flex: "1 1 18rem" }}><span>Find</span>
              <input className="reg-box" placeholder="Name, PARAKH id, APAAR, admission no." value={find}
                     onChange={(e) => { setFind(e.target.value); setPage(0); }} /></label>
          </div>
          <div className="sdms-scroll"><table className="sdms-table sdms-fit">
            <thead><tr><th>Stage</th><th>Class</th><th>Name (as on PARAKH)</th><th>PARAKH id</th><th>APAAR</th><th>Admission no.</th>
              <th>DOB</th><th>Teacher</th><th>Attendance</th><th>Parents</th><th>Marks</th><th>Card on PARAKH</th></tr></thead>
            <tbody>{rows.slice(at * PAGE_SIZE, (at + 1) * PAGE_SIZE).map((s) => (
              <tr key={s.id} className={s.missing_on_parakh ? "lib-muted" : ""}>
                <td>{s.stage}</td><td>{s.grade} {s.section}</td><td><b>{s.student_name}</b></td><td>{s.student_id}</td>
                <td>{s.apaar_id || "—"}</td><td>{s.admission_number || "—"}</td><td>{s.dob || "—"}</td>
                <td className={s.teachers.length ? "" : "sdms-warn"}>{s.teachers.join(", ") || "No teacher"}</td>
                <td>{s.entered?.months ? `${s.entered.present}/${s.entered.working}${s.entered.percent != null ? ` (${s.entered.percent}%)` : ""}` : "—"}</td>
                <td>{s.entered?.father || s.entered?.mother ? [s.entered.father, s.entered.mother].filter(Boolean).join(" / ") : "—"}</td>
                <td>{s.entered && s.entered.marks_of ? `${s.entered.marks} of ${s.entered.marks_of}` : "—"}</td>
                <td className={CARD_TONE[s.card?.status || ""] || ""}>{s.card?.status || "—"}
                  {s.card && (s.card.detail || s.card.teacher || s.card.at) && <small>{[s.card.detail, s.card.teacher,
                    s.card.at && new Date(s.card.at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })].filter(Boolean).join(" · ")}</small>}</td></tr>))}
            </tbody>
          </table></div>
          {pages > 1 && (
            <nav className="sdms-pager" aria-label="Student pages">
              <button type="button" className="btn btn-outline btn-sm" onClick={() => setPage(at - 1)} disabled={at === 0}>Previous</button>
              <span>Page {at + 1} of {pages} · students {at * PAGE_SIZE + 1}–{Math.min(rows.length, (at + 1) * PAGE_SIZE)} of {rows.length}</span>
              <button type="button" className="btn btn-outline btn-sm" onClick={() => setPage(at + 1)} disabled={at >= pages - 1}>Next</button>
            </nav>
          )}
          <p className="lib-muted">{rows.length} of {reg.students.length} students match.</p>
        </div>
      )}
    </div>
  );
}

// ─── Phase 2: what the school sets and enters once ───────────────────────────

const MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"];
interface Settings { stage: string; session: string; version: number; updated_at: string | null;
  values: { working_days: (number | null)[]; max_marks: Record<string, number | null> }; subjects: { n: string; name: string }[] }

export function SchoolSettings({ api }: { api: Api }) {
  const [stage, setStage] = useState("Preparatory");
  const [s, setS] = useState<Settings | null>(null);
  const [days, setDays] = useState<string[]>([]);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(async () => {
    setMsg(null);
    try {
      const r = await call<Settings>(api, "GET", `/school/register/settings?stage=${stage}`);
      setS(r);
      setDays(r.values.working_days.map((d) => (d === null ? "" : String(d))));
      setMarks(Object.fromEntries(r.subjects.map((x) => [x.n, r.values.max_marks[x.n] == null ? "" : String(r.values.max_marks[x.n])])));
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }, [api, stage]);
  useEffect(() => { void load(); }, [load]);
  const save = async () => {
    try {
      const r = await call<Settings>(api, "PUT", "/school/register/settings", { stage, values: {
        working_days: days.map((d) => (d.trim() === "" ? null : d.trim())),
        max_marks: Object.fromEntries(Object.entries(marks).map(([n, m]) => [n, m.trim() === "" ? null : m.trim()])) } });
      setS(r);
      setMsg({ ok: true, text: `Saved (version ${r.version}). Teachers see these; they cannot change them.` });
    } catch (e) {
      const text = (e as Error).message;
      try { setMsg({ ok: false, text: Object.values(JSON.parse(text) as Record<string, string>).join("; ") }); }
      catch { setMsg({ ok: false, text }); }
    }
  };
  return (
    <div className="ui-panel">
      <h3 className="lib-section-title">Working days and max marks (set by the school)</h3>
      <div className="reg-toolbar">
        <label className="reg-field">
          <span>Stage</span>
          <select className="reg-box" value={stage} onChange={(e) => setStage(e.target.value)}>
            {STAGES.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        {s && <span className="lib-muted">Year {s.session.slice(0, 2)}-{s.session.slice(2)} · {s.version ? `version ${s.version}` : "not set yet"}</span>}
      </div>
      {s && (<>
        <b>Working days in each month</b>
        <div className="reg-grid">{days.map((d, i) => (
          <label key={i} className="reg-field">
            <span>{MONTHS[i]}</span>
            <input className="reg-box" inputMode="numeric" value={d} placeholder="—"
                   onChange={(e) => setDays((p) => p.map((x, j) => (j === i ? e.target.value : x)))} />
          </label>))}
        </div>
        {s.subjects.length > 0 ? (<>
          <b>Summative max marks</b>
          <div className="reg-grid wide">{s.subjects.map((x) => (
            <label key={x.n} className="reg-field">
              <span>{x.name}</span>
              <input className="reg-box" inputMode="numeric" value={marks[x.n] ?? ""} placeholder="—"
                     onChange={(e) => setMarks((p) => ({ ...p, [x.n]: e.target.value }))} />
            </label>))}
          </div>
        </>) : <p className="lib-muted">Foundational has no summative marks on PARAKH.</p>}
        <button type="button" className="btn btn-primary" onClick={save}>Save for {stage}</button>
      </>)}
      {msg && <p className={msg.ok ? "lib-muted" : "sdms-warn"} role="status">{msg.text}</p>}
    </div>
  );
}

interface CheckRow { sheet: string; row: number; parakh_id: string; name: string; outcome: "ready" | "problem" | "review"; problems: string[]; changes: string[] }
interface Check { id: string; file_name: string; status: string; created_at: string; applied_at: string | null; rows: CheckRow[];
  summary: { ready: number; unchanged: number; problem: number; review: number; left_out: Record<string, number>; already_applied_at: string | null } }
interface Hist { id: string; file_name: string; status: string; summary: Check["summary"]; created_at: string; applied_at: string | null }
const FIELD_NAMES: Record<string, string> = { father_name: "father", mother_name: "mother", guardian_relation: "name on card",
  guardian_name: "guardian", present: "days present", marks: "marks" };

export function SchoolData({ api, onSaved }: { api: Api; onSaved: () => void }) {
  const [check, setCheck] = useState<Check | null>(null);
  const [hist, setHist] = useState<Hist[]>([]);
  const [udise, setUdise] = useState<{ fetched_at: string | null; kind: "full" | "quick" | null; students: number } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const r = await call<{ check: Check | null; history: Hist[]; parents_source: typeof udise }>(api, "GET", "/school/register/data");
      setCheck(r.check);
      setHist(r.history);
      setUdise(r.parents_source);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  const upload = async (file: File) => {
    setBusy("checking");
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/register/data/check", { method: "POST", body: form }, api.base);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The workbook could not be checked.");
      setCheck(body as Check);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const apply = async () => {
    if (!check || !window.confirm(`Save ${check.summary.ready} students' data into the School Register?`)) return;
    setBusy("saving");
    try {
      await call(api, "POST", "/school/register/data/apply", { import_id: check.id, confirm: true });
      await load();
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
  const download = async () => setError(await downloadSheet(api, "/school/register/data.xlsx", "School_Data.xlsx"));
  // students admitted on UDISE+ since its last read have no parents' names yet: read UDISE+ again, then download
  const freshDownload = async () => {
    setBusy("udise");
    setError(null);
    try {
      await call(api, "POST", "/school/register/parents/fetch");
      await load();
      await download();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="ui-panel">
      <h3 className="lib-section-title">School Data: attendance, parents, marks</h3>
      <p className="lib-muted">Download the workbook (every student from the register, parents' names from UDISE+ where found),
        fill days present per month, whose name the HPC card shows and marks obtained, and upload it here. It is checked
        first; nothing is saved until you press Save. Monthly totals only.</p>
      <div className="sdms-actions">
        <button type="button" className="btn btn-outline" disabled={!!busy} onClick={download}
                title="Parents' names from the UDISE+ data the app already has">
          <Download size={15} aria-hidden="true" /> Download School Data workbook
        </button>
        <button type="button" className="btn btn-outline" disabled={!!busy} onClick={freshDownload}
                title="Reads UDISE+ again first (needs UDISE+ connected) - for students admitted since">
          <RefreshCw size={15} aria-hidden="true" className={busy === "udise" ? "spin" : ""} />
          {busy === "udise" ? " Reading UDISE+…" : " Fetch parents from UDISE+, then download"}
        </button>
        <label className="btn btn-outline sdms-upload">
          <Upload size={15} aria-hidden="true" /> {busy === "checking" ? "Checking…" : "Upload filled workbook"}
          <input type="file" accept=".xlsx" hidden disabled={!!busy}
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </label>
      </div>
      <p className="lib-muted">{udise?.fetched_at
        ? <>Parents' names come from UDISE+ as read on <b>{when(udise.fetched_at)}</b> ({udise.students} students). Students
            admitted on UDISE+ after that have none: use "Fetch parents from UDISE+, then download".</>
        : <>No UDISE+ data yet: use "Fetch parents from UDISE+, then download" (connect UDISE+ on the Home page first).</>}</p>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      {check && (
        <div className="sdms-plan">
          <p><b>{check.file_name}</b> ({when(check.created_at)}): <b>{check.summary.ready}</b> ready to save,{" "}
            {check.summary.unchanged} unchanged, <span className={check.summary.problem ? "sdms-warn" : ""}>{check.summary.problem} to correct</span>,{" "}
            <span className={check.summary.review ? "sdms-warn" : ""}>{check.summary.review} to review (identity changed)</span>
            {Object.keys(check.summary.left_out).length > 0 && <> · left out of the file: {Object.entries(check.summary.left_out).map(([s, n]) => `${s} ${n}`).join(", ")}</>}
            {check.summary.already_applied_at && <> · this same file was saved on {when(check.summary.already_applied_at)}</>}
            {check.status === "APPLIED" && <> · <b>saved {when(check.applied_at)}</b></>}</p>
          {check.rows.length > 0 && (
            <div className="sdms-scroll"><table className="sdms-table sdms-fit">
              <thead><tr><th>Sheet, row</th><th>Student</th><th>Outcome</th><th>Details</th></tr></thead>
              <tbody>{check.rows.map((r) => (
                <tr key={`${r.sheet}${r.row}`}><td>{r.sheet} {r.row}</td><td>{r.name} <small>{r.parakh_id}</small></td>
                  <td className={r.outcome === "ready" ? "" : "sdms-warn"}>{r.outcome === "ready" ? "Ready" : r.outcome === "review" ? "Review" : "Correct"}</td>
                  <td>{r.problems.length ? r.problems.join("; ") : `Changes: ${r.changes.map((c) => FIELD_NAMES[c] || c).join(", ")}`}</td></tr>))}
              </tbody></table></div>)}
          {check.status === "CHECKED" && check.summary.ready > 0 && (
            <button type="button" className="btn btn-primary" disabled={!!busy} onClick={apply}>
              {busy === "saving" ? "Saving…" : `Save ${check.summary.ready} students into the School Register`}</button>)}
        </div>
      )}
      {hist.length > 0 && (
        <details><summary>Import history ({hist.length})</summary>
          <table className="sdms-table sdms-fit"><thead><tr><th>Uploaded</th><th>File</th><th>Status</th><th>Ready / to correct / review</th></tr></thead>
            <tbody>{hist.map((h) => (
              <tr key={h.id}><td>{when(h.created_at)}</td><td>{h.file_name}</td>
                <td>{h.status === "APPLIED" ? `Saved ${when(h.applied_at)}` : h.status === "CHECKED" ? "Checked, not saved" : "Replaced by a later check"}</td>
                <td>{h.summary.ready} / {h.summary.problem} / {h.summary.review}</td></tr>))}
            </tbody></table>
        </details>)}
    </div>
  );
}

// ─── Phase 6: UDISE+ · APAAR · PARAKH on the school's dashboard, and the reports ───────────────────────────────

interface Recon { ok: boolean; error?: string; source?: string; differs?: Record<string, number>;
  counts?: { udise: number; parakh: number; matched: number; differ: number; only_udise: number; only_parakh: number };
  apaar?: { missing_both: number; only_udise: number; only_parakh: number; differ: number; unmatched_without: number } }

export function SchoolDashboard({ api }: { api: Api }) {
  const [r, setR] = useState<Recon | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { call<Recon>(api, "GET", "/school/register/reports/reconciliation").then(setR).catch((e) => setError((e as Error).message)); }, [api]);
  const tile = (label: string, value: number | undefined, warn = false) => (
    <div className="reg-field" style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "0.6rem 0.8rem", background: "#fff" }}>
      <span>{label}</span><b className={warn && value ? "sdms-warn" : ""} style={{ fontSize: "1.35rem" }}>{value ?? "—"}</b></div>);
  return (
    <div className="ui-panel">
      <h3 className="lib-section-title">UDISE+ · APAAR · PARAKH</h3>
      {error && <p className="sdms-warn">{error}</p>}
      {r && !r.ok && <p className="lib-muted">{r.error}</p>}
      {r?.ok && r.counts && r.apaar && (<>
        <p className="lib-muted">Compared from the {r.source} with UDISE+ (SDMS) as last fetched - by APAAR ID, then admission
          number, then name and date of birth.</p>
        <div className="reg-grid wide">
          {tile("On UDISE+", r.counts.udise)}{tile("On PARAKH", r.counts.parakh)}{tile("Matched", r.counts.matched)}
          {tile("Matched, with differences", r.counts.differ, true)}{tile("Only on UDISE+", r.counts.only_udise, true)}
          {tile("Only on PARAKH", r.counts.only_parakh, true)}
        </div>
        <b>APAAR</b>
        <div className="reg-grid wide">
          {tile("Missing on both", r.apaar.missing_both, true)}{tile("Only on PARAKH", r.apaar.only_parakh, true)}
          {tile("Only on UDISE+", r.apaar.only_udise, true)}{tile("Different", r.apaar.differ, true)}
          {tile("Not matched, no APAAR", r.apaar.unmatched_without, true)}
        </div>
        {r.differs && Object.keys(r.differs).length > 0 && (
          <p className="lib-muted">Differences: {Object.entries(r.differs).map(([k, n]) => `${k} ${n}`).join(" · ")}</p>)}
      </>)}
      <div className="sdms-actions">
        <button type="button" className="btn btn-primary"
                onClick={async () => setError(await downloadSheet(api, "/school/register/reports/reconciliation.xlsx", "UDISE_APAAR_PARAKH_report.xlsx"))}>
          <Download size={15} aria-hidden="true" /> UDISE+ · APAAR · PARAKH report (Excel)</button>
        <button type="button" className="btn btn-outline"
                onClick={async () => setError(await downloadSheet(api, "/school/register/reports/school.xlsx", "School_Register_report.xlsx"))}>
          <Download size={15} aria-hidden="true" /> School report: students, teachers, attendance, marks (Excel)</button>
      </div>
    </div>
  );
}
