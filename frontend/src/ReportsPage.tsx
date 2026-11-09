import { useState } from "react";
import { AlertCircle, FileDown, GitCompare, RefreshCw } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";
import { downloadSheet } from "./downloadSheet";
import { CardHub } from "./CardHub";

// Printable PDF reports of each pendency, and UDISE+ against PARAKH: who is on one and not the other, and matched
// students whose details differ. Everything comes from the app's last reads of SDMS and PARAKH (nothing is sent).

interface Side { name: string; parent: string; adm_no: string; class: string; dob: string; apaar: string; status: string; pen?: string }
interface Match { by: string; udise: Side; parakh: Side; differs: string[] }
interface Compare {
  counts: { udise: number; parakh: number; matched: number; only_udise: number; only_parakh: number; differ: number; udise_higher_classes: number };
  only_udise: Side[]; only_parakh: Side[]; matched: Match[];
}
type Tab = "only_parakh" | "only_udise" | "differ";

const REPORTS = [
  { name: "aadhaar", file: "AADHAAR_pending.pdf", title: "AADHAAR pending", about: "Students not verified with UIDAI, grouped by reason, with what to do." },
  { name: "apaar", file: "APAAR_status.pdf", title: "APAAR ID status", about: "Pending with SDMS's reason and the next step; then the IDs generated." },
  { name: "completion", file: "SDMS_forms_pending.pdf", title: "SDMS forms pending", about: "Each student's required fields still empty or wrong." },
  { name: "profile", file: "UDISE_School_Profile_status.pdf", title: "School Profile & Facilities", about: "Each yearly form: what is still needed (DCF item, workbook sheet and row) and what the app updated." },
  { name: "teachers", file: "UDISE_Teachers_status.pdf", title: "Teacher module (staff)", about: "Each staff member: what is still needed (sheet and cell in the Excel) and what the app updated." },
  { name: "compare", file: "UDISE_vs_PARAKH.pdf", title: "UDISE+ vs PARAKH", about: "On one and not the other, and details that differ." },
];

// Records to download only (Excel): nothing to fill and upload back - those are on the Bulk Excel page
const RECORDS = [
  { key: "hpc-records", path: "/school/hpc/records.xlsx", file: "HPC_records.xlsx", title: "HPC records (everything entered)",
    about: "Every student's HPC card as the app keeps it - every part, every answer, in words - for the school's records." },
  { key: "apaar-status", path: "/school/udise/sdms/apaar/status.xlsx", file: "APAAR_status.xlsx", title: "APAAR status",
    about: "Every student's APAAR: generated (with the ID) or pending with SDMS's reason and what to do next." },
  { key: "reconciliation", path: "/school/register/reports/reconciliation.xlsx", file: "UDISE_APAAR_PARAKH_report.xlsx",
    title: "UDISE+ / APAAR / PARAKH", about: "Matched students, APAAR on both sides, the differences, and who is only on one side." },
  { key: "school-report", path: "/school/register/reports/school.xlsx", file: "School_Register_report.xlsx", title: "School report",
    about: "Every student with teacher, card status, attendance, parents and marks; by teacher; who needs attention." },
];

export function ReportsPage({ api }: { api: Api }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [tab, setTab] = useState<Tab>("only_parakh");

  const pdf = async (name: string, file: string) => {
    setBusy(name);
    setError(await downloadSheet(api, `/school/udise/reports/${name}.pdf`, file));
    setBusy(null);
  };
  const excel = async (key: string, path: string, file: string) => {
    setBusy(key);
    setError(await downloadSheet(api, path, file));
    setBusy(null);
  };
  const compare = async () => {
    setBusy("view");
    setError(null);
    try {
      setCmp(await call<Compare>(api, "GET", "/school/udise/compare"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const c = cmp?.counts;
  const side = (rows: Side[], pen: boolean) => (
    <table className="sdms-table sdms-fit">
      <thead><tr><th>Student</th><th>Parentage</th><th>Adm. no</th><th>Class</th><th>DOB</th><th>APAAR ID</th><th>Status</th>{pen && <th>PEN</th>}</tr></thead>
      <tbody>
        {rows.map((s, i) => (
          <tr key={i}><td><b>{s.name}</b></td><td>{s.parent || "—"}</td><td>{s.adm_no || "—"}</td><td>{s.class}</td><td>{s.dob || "—"}</td>
            <td>{s.apaar || "—"}</td><td>{s.status}</td>{pen && <td>{s.pen || "—"}</td>}</tr>
        ))}
        {rows.length === 0 && <tr><td colSpan={pen ? 8 : 7} className="lib-muted">None.</td></tr>}
      </tbody>
    </table>
  );
  const differ = (cmp?.matched || []).filter((m) => m.differs.length);
  const comparePanel = (
      <div className="ui-panel">
        <div className="sdms-head">
          <span />
          <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={compare}>
            {busy === "view" ? <RefreshCw size={15} className="spin" aria-hidden="true" /> : <GitCompare size={15} aria-hidden="true" />} Compare now
          </button>
        </div>
        <p className="lib-muted">A student is the same on both when the APAAR ID matches, else the admission number, else the name with the date of birth,
          else the name with the parent's name. Parentage on PARAKH is the guardian's name in Part A1.</p>
        {c && (
          <>
            <div className="report-tiles">
              <span><b>{c.udise}</b>On UDISE+</span><span><b>{c.parakh}</b>On PARAKH</span><span className="good"><b>{c.matched}</b>On both</span>
              <span className="bad"><b>{c.only_parakh}</b>Only on PARAKH</span><span className="bad"><b>{c.only_udise}</b>Only on UDISE+</span>
              <span className="warn"><b>{c.differ}</b>Details differ</span>
            </div>
            {c.udise_higher_classes > 0 && <p className="lib-muted">{c.udise_higher_classes} UDISE+ students in classes PARAKH does not cover are left out.</p>}
            <div className="report-tabs" role="tablist">
              {([["only_parakh", `On PARAKH, not on UDISE+ (${c.only_parakh})`], ["only_udise", `On UDISE+, not on PARAKH (${c.only_udise})`],
                 ["differ", `Details differ (${c.differ})`]] as [Tab, string][]).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} className={`btn ${tab === k ? "btn-primary" : "btn-outline"}`}
                        onClick={() => setTab(k)}>{label}</button>
              ))}
            </div>
            <div className="report-scroll">
              {tab === "only_parakh" && side(cmp!.only_parakh, false)}
              {tab === "only_udise" && side(cmp!.only_udise, true)}
              {tab === "differ" && (
                <table className="sdms-table sdms-fit">
                  <thead><tr><th>Student (UDISE+)</th><th>Parentage</th><th>Class UDISE+ / PARAKH</th><th>Adm. no UDISE+ / PARAKH</th>
                    <th>DOB UDISE+ / PARAKH</th><th>Matched by</th><th>Differs in</th></tr></thead>
                  <tbody>
                    {differ.map((m, i) => (
                      <tr key={i}><td><b>{m.udise.name}</b>{m.differs.includes("name") && <small>PARAKH: {m.parakh.name}</small>}</td>
                        <td>{m.udise.parent || "—"}</td><td>{m.udise.class} / {m.parakh.class}</td>
                        <td>{m.udise.adm_no || "—"} / {m.parakh.adm_no || "—"}</td><td>{m.udise.dob} / {m.parakh.dob}</td>
                        <td>{m.by}</td><td className="sdms-warn">{m.differs.join(", ")}</td></tr>
                    ))}
                    {differ.length === 0 && <tr><td colSpan={7} className="lib-muted">None.</td></tr>}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
  );

  return (
    <div className="sdms-page">
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      <p className="lib-muted">Made from the last fetch of the students from SDMS (and the classes fetched from PARAKH). Fetch again first for today's position.</p>
      <CardHub label="Reports" cards={[
        ...REPORTS.map((r) => ({ key: r.name, title: r.title, about: r.about, icon: FileDown, statLabel: busy === r.name ? "making…" : "PDF",
                                 stat: busy === r.name ? <RefreshCw size={20} className="spin" aria-hidden="true" /> : "",
                                 onOpen: () => { if (busy === null) void pdf(r.name, r.file); } })),
        ...RECORDS.map((r) => ({ key: r.key, title: r.title, about: r.about, icon: FileDown, statLabel: busy === r.key ? "making…" : "Excel",
                                 stat: busy === r.key ? <RefreshCw size={20} className="spin" aria-hidden="true" /> : "",
                                 onOpen: () => { if (busy === null) void excel(r.key, r.path, r.file); } })),
        { key: "compare-view", title: "Compare on screen", icon: GitCompare, tone: "info" as const,
          about: "UDISE+ and PARAKH side by side: who is on one only, and the details that differ.", body: () => comparePanel },
      ]} />
    </div>
  );
}
