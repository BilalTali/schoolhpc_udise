import { useCallback, useEffect, useState } from "react";
import { AlertCircle, ArrowRightLeft, Building2, CheckCircle2, ClipboardCheck, Download, FileSpreadsheet, Fingerprint, IdCard, Inbox,
  RefreshCw, School, Upload, UserPlus, Users } from "lucide-react";
import { ApaarSheet } from "./ApaarSheet";
import { ProfilePage } from "./ProfilePage";
import { SchoolData } from "./RegisterPage";
import { SdmsAdmit } from "./SdmsAdmit";
import { SdmsUpdate } from "./SdmsUpdate";
import { TeachersPage } from "./TeachersPage";
import type { LucideIcon } from "lucide-react";
import { CardHub } from "./CardHub";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";
import { downloadSheet } from "./downloadSheet";

// Bulk tools on SDMS, each the way SDMS's own page does it, for many students from one Excel sheet: download -> fill ->
// upload (checked here, nothing sent) -> one student first, then all, each after confirming. A row done once is never
// sent again; a row SDMS refused stays ready to send after it is corrected.

type Kind = "shift" | "dropbox" | "import" | "aadhaar";
interface Row { row: number; pen: string; name: string | null; class?: string; change: string; problems: string[]; done: string | null }
interface Plan { file_name: string; rows: Row[]; ready: number; with_problems: number; done: number }
interface Result { row: number; name: string | null; change: string; message: string | null; error: string | null }
interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; results: Result[]; error: string | null }

const TOOLS: { kind: Kind; title: string; file: string; about: string; confirm: string }[] = [
  { kind: "shift", title: "Class or section shift", file: "Class_section_shift.xlsx",
    about: "Move students to another section of their class. SDMS allows a class change only between Nursery/KG and Class I.",
    confirm: "move these students to their new class or section on SDMS" },
  { kind: "dropbox", title: "Send to Dropbox", file: "Send_to_Dropbox.xlsx",
    about: "Students who left: with a TC (with the TC date and reason) or without (dropout, absent for many days). Mid session means the student studied here this year; end session means not this year.",
    confirm: "send these students to the Dropbox on SDMS (they leave this school's list)" },
  { kind: "import", title: "Import from the Dropbox", file: "Import_from_Dropbox.xlsx",
    about: "Admit students who are in the Dropbox (left another school). The PEN and date of birth find each one on SDMS when the sheet is checked; the progression status must be one SDMS offers for that class.",
    confirm: "import these students into this school on SDMS" },
  { kind: "aadhaar", title: "AADHAAR (UID) corrections", file: "AADHAAR_corrections.xlsx",
    about: "The students whose AADHAAR is not verified. Copy the details exactly as on each AADHAAR card; each is saved on SDMS, then checked with UIDAI (demographic authentication).",
    confirm: "save these AADHAAR details on SDMS and check them with UIDAI. You confirm each parent gave consent for demographic authentication" },
];

const ICONS: Record<Kind, LucideIcon> = { shift: ArrowRightLeft, dropbox: Inbox, import: UserPlus, aadhaar: Fingerprint };

// Every bulk Excel of the app on one page: each card opens the same panel its own page uses (nothing works differently).
export function BulkTools({ api }: { api: Api }) {
  const sdms = (sheet: "students" | "completion" | "new-admissions", label: string) => (
    <button type="button" className="btn btn-outline" onClick={async () => alertIf(await downloadSheet(api, `/school/udise/sdms/${sheet}.xlsx`,
      `SDMS_${sheet}.xlsx`))}><Download size={15} aria-hidden="true" /> {label}</button>);
  const cards = [
    { key: "details", title: "Update student details (SDMS)", icon: FileSpreadsheet, stat: "SDMS", statLabel: "download · upload",
      about: "Every student's full SDMS form in Excel: change any coloured column and upload it back to update SDMS.",
      body: () => <div className="ui-panel">{sdms("students", "Download all details (Excel)")}<SdmsUpdate api={api} full onSaved={() => undefined} /></div> },
    { key: "completion", title: "Complete incomplete SDMS forms", icon: ClipboardCheck, stat: "SDMS", statLabel: "download · upload",
      about: "Only the students whose SDMS form is not complete, with just the fields still missing: fill the yellow cells, upload, save.",
      body: () => <div className="ui-panel">{sdms("completion", "Download incomplete forms only")}<SdmsUpdate api={api} onSaved={() => undefined} /></div> },
    { key: "admit", title: "New admissions (SDMS)", icon: UserPlus, stat: "SDMS", statLabel: "download · upload",
      about: "Add new students from one sheet: checked first, added on SDMS only when you press Add.",
      body: () => <div className="ui-panel">{sdms("new-admissions", "Download new admissions sheet")}<SdmsAdmit api={api} onAdded={() => undefined} /></div> },
    ...TOOLS.map((t) => ({ key: t.kind, title: t.title, about: t.about, icon: ICONS[t.kind], stat: "SDMS", statLabel: "download · upload",
                           body: () => <BulkTool api={api} tool={t} /> })),
    { key: "apaar", title: "APAAR generation (consent sheet)", icon: IdCard, stat: "APAAR", statLabel: "download · upload",
      about: "Generate APAAR IDs in bulk from the parents' physical consent: download, fill each consent, upload, generate.",
      body: () => <ApaarCard api={api} /> },
    { key: "profile", title: "School profile & facilities (UDISE+)", icon: School, stat: "Profile", statLabel: "download · upload",
      about: "The yearly school forms (DCF 1.31 to 2.28): download, fill, upload, check and save.", body: () => <ProfilePage api={api} /> },
    { key: "staff", title: "Teachers and staff (UDISE+)", icon: Users, stat: "Teachers", statLabel: "download · upload",
      about: "Every staff member's forms on the UDISE+ Teacher module: download, fill, upload and check.", body: () => <TeachersPage api={api} /> },
    { key: "school-data", title: "School Data: attendance, parents, marks", icon: Building2, stat: "School Register", statLabel: "download · upload",
      about: "Days present per month, the name on the HPC card and summative marks for every student; goes to the teachers' cards.",
      body: () => <SchoolData api={api} onSaved={() => undefined} /> },
  ];
  return (
    <div className="sdms-page">
      <p className="lib-muted">Every Excel you download, fill and upload back, in one place (files you only download are on Reports). SDMS, APAAR, profile and staff sheets need UDISE+ connected
        (fetch the students on Students (SDMS) first); School Register sheets need the register fetched from PARAKH.</p>
      <CardHub label="Bulk Excel" cards={cards} />
    </div>
  );
}

function alertIf(message: string | null) {
  if (message) window.alert(message);
}

function ApaarCard({ api }: { api: Api }) {
  const [ready, setReady] = useState<number | null>(null);
  const load = useCallback(async () => {
    try {
      const v = await call<{ apaar_read: boolean; counts: { apaar_ready: number } }>(api, "GET", "/school/udise/sdms/aadhaar");
      setReady(v.apaar_read ? v.counts.apaar_ready : 0);
    } catch {
      setReady(0);
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  return ready === null ? <p className="lib-muted">Loading…</p> : <ApaarSheet api={api} ready={ready} onDone={() => { void load(); }} />;
}

function BulkTool({ api, tool }: { api: Api; tool: (typeof TOOLS)[number] }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [first, setFirst] = useState<number | "">("");
  const base = `/school/udise/sdms/bulk/${tool.kind}`;

  const look = useCallback(async () => {
    try {
      const r = await call<{ plan: Plan | null; job: Job | null }>(api, "GET", base);
      setPlan(r.plan);
      setJob(r.job);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, base]);
  useEffect(() => { void look(); }, [look]);
  const running = job?.status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => { void look(); }, 2000);
    return () => window.clearTimeout(t);
  }, [running, job, look]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch(`${base}/validate`, { method: "POST", body: form }, api.base);
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

  const send = async (rows: number[] | null) => {
    const who = rows ? plan?.rows.find((r) => r.row === rows[0])?.name || `row ${rows[0]}` : `${plan?.ready} students`;
    if (!window.confirm(`For ${who}: ${tool.confirm}. Go ahead?`)) return;
    setBusy(true);
    setError(null);
    try {
      await call(api, "POST", `${base}/run`, { confirm: true, rows });
      await look();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ok = (plan?.rows || []).filter((r) => !r.problems.length && !r.done);
  return (
    <div className="ui-panel">
      <p className="lib-muted">{tool.about}</p>
      <div className="sdms-actions">
        <button type="button" className="btn btn-outline" disabled={busy}
                onClick={async () => setError(await downloadSheet(api, `${base}/sheet.xlsx`, tool.file))}>
          <Download size={15} aria-hidden="true" /> Download the sheet
        </button>
        <label className="btn btn-outline sdms-upload">
          <Upload size={15} aria-hidden="true" /> {busy && !running ? "Checking…" : "Upload the filled sheet"}
          <input type="file" accept=".xlsx" hidden disabled={busy || running}
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </label>
      </div>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}

      {plan && !running && (
        <div className="sdms-plan">
          <p><b>{plan.file_name}</b>: <b>{plan.ready}</b> ready
            {plan.with_problems > 0 && <>, <b className="sdms-warn">{plan.with_problems}</b> to correct</>}
            {plan.done > 0 && <>, {plan.done} done already</>}.</p>
          <ul className="sdms-plan-list">
            {plan.rows.map((r) => (
              <li key={r.row}><b>{r.name || r.pen}</b>{r.class ? ` · ${r.class}` : ""} · row {r.row} · {r.change}
                {r.done ? <span> · <CheckCircle2 size={13} aria-hidden="true" /> done</span>
                  : r.problems.length ? <p className="sdms-warn">Correct in the sheet: {r.problems.join("; ")}</p>
                  : <span className="lib-muted"> · ready</span>}
              </li>
            ))}
          </ul>
          {ok.length > 0 && (
            <div className="sdms-actions">
              <select className="form-input" value={first} onChange={(e) => setFirst(e.target.value ? Number(e.target.value) : "")}
                      aria-label="The student to send first">
                <option value="">Choose one student to try first…</option>
                {ok.map((r) => <option key={r.row} value={r.row}>{r.name || r.pen} (row {r.row})</option>)}
              </select>
              <button type="button" className="btn btn-outline" disabled={busy || first === ""} onClick={() => send([first as number])}>
                Send this one
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => send(null)}>Send all {plan.ready}</button>
            </div>
          )}
        </div>
      )}

      {job && (
        <div className="sdms-progress" role="status">
          {running && <div><RefreshCw size={14} className="spin" aria-hidden="true" /> <b>Sending to SDMS…</b> {job.done} of {job.total}</div>}
          {job.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
          {job.results.length > 0 && (
            <table className="sdms-table sdms-fit">
              <thead><tr><th>Student</th><th>Change</th><th>Result</th></tr></thead>
              <tbody>
                {job.results.map((r) => (
                  <tr key={r.row}>
                    <td><b>{r.name}</b><small>row {r.row}</small></td>
                    <td>{r.change}</td>
                    <td className={r.error ? "sdms-warn" : ""}>{r.error || <><CheckCircle2 size={14} aria-hidden="true" /> {r.message}</>}</td>
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
