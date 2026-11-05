import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileDown, RefreshCw, Upload } from "lucide-react";
import { downloadSheet, saveBlob } from "./downloadSheet";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";

// UDISE+ School Profile & Facilities for the current session (DCF 1.31 to 2.28): see each form as UDISE+ holds it,
// download the year's answers as Excel, upload it back -> checked here (nothing sent) -> save, after confirming.
// Certifying stays on the UDISE+ website.

interface FormRow { key: string; dcf: string; title: string; sheet: string; questions: number; answered: number; needed: number;
  error: string | null; year: string; modified: string; certified: boolean }
interface Needed { form: string; dcf: string; title: string; item: string; question: string; sheet: string; row: number; allowed: string }
interface Updated { at: string; year: string; dcf: string; title: string; sheet: string; item: string; question: string;
  before: string | number | null; after: string | number | null; result: string }
interface Change { id: string; item: string; question: string; old: string | number | null; new: string | number | null; warning: string }
interface Problem { item: string; question: string; message: string }
interface PlanForm { key: string; dcf: string; title: string; certified: boolean; changes: Change[]; problems: Problem[] }
interface Result { key: string; dcf: string; status: "saved" | "check" | "skipped" | "refused" | "error"; message: string; saved?: number; skipped?: string[] }
interface Plan { file_name: string; checked_at: string; year: string; forms: PlanForm[]; total_changes: number; blocked_forms: string[];
  results: { at: string; forms: Result[] } | null }
interface Overview { school: { name: string; udise_code: string; category: string; session_from: string; session_to: string };
  year: string; forms: FormRow[]; needed: Needed[]; problems: { dcf: string; title: string; message: string }[];
  updated: Updated[]; read_at: string; plan: Plan | null }

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
const STATUS: Record<Result["status"], string> = { saved: "Saved and confirmed on UDISE+", check: "Saved - check on UDISE+",
  skipped: "Not saved", refused: "UDISE+ refused", error: "Not saved" };

export function ProfilePage({ api }: { api: Api }) {
  const [data, setData] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState<"" | "reading" | "download" | "checking" | "saving">("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy("reading");
    setError(null);
    try {
      const r = await call<Overview>(api, "GET", "/school/udise/profile");
      setData(r);
      setPlan(r.plan);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);

  const download = async () => {
    setBusy("download");
    setError(null);
    try {
      const res = await apiFetch("/school/udise/profile.xlsx", {}, api.base);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(`The workbook could not be made${body?.detail ? `: ${body.detail}` : ` (error ${res.status})`}.`);
      }
      const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "UDISE_School_Profile.xlsx";
      saveBlob(await res.blob(), name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const upload = async (file: File) => {
    setBusy("checking");
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/udise/profile/validate", { method: "POST", body: form }, api.base);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : "The workbook could not be checked.");
      setPlan(body as Plan);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const save = async (only: string[] | null) => {
    if (!plan) return;
    const certified = plan.forms.some((f) => f.certified && (!only || only.includes(f.key)));
    const what = only ? plan.forms.find((f) => f.key === only[0])?.dcf : `${plan.total_changes} change${plan.total_changes === 1 ? "" : "s"}`;
    if (!window.confirm(`Save ${what} to UDISE+ now? This changes the school's data on UDISE+.`
      + (certified ? "\n\nA form that is already certified loses its certification: certify again on UDISE+ afterwards." : ""))) return;
    setBusy("saving");
    setError(null);
    try {
      await call(api, "POST", "/school/udise/profile/save", { confirm: true, only });
      await load();
    } catch (e) {
      setError((e as Error).message);
      setBusy("");
    }
  };

  const ready = (plan?.forms || []).filter((f) => !f.problems.length && f.changes.some((c) => !c.warning));
  return (
    <div className="sdms">
      <div className="ui-panel">
        <div className="sdms-head">
          <div>
            <h2 className="sdms-title">School Profile & Facilities</h2>
            <p className="lib-muted">
              {data ? <>Session <b>{data.year}</b> · {data.school.name} ({data.school.udise_code}) · {data.school.category}
                        {data.school.session_from && <> · academic year {data.school.session_from} to {data.school.session_to}</>}
                        {" "}· read {when(data.read_at)}</>
                    : "The forms the school fills every year on UDISE+ (DCF 1.31 to 2.28)."}
            </p>
          </div>
          <div className="sdms-actions">
            <button type="button" className="btn btn-outline" disabled={!!busy}
                    onClick={async () => { setError(await downloadSheet(api, "/school/udise/reports/profile.pdf", "UDISE_School_Profile_status.pdf")); }}>
              <FileDown size={15} aria-hidden="true" /> Status report (PDF)
            </button>
            <button type="button" className="btn btn-outline" onClick={load} disabled={!!busy}>
              <RefreshCw size={15} aria-hidden="true" className={busy === "reading" ? "spin" : ""} /> Read again
            </button>
            <button type="button" className="btn btn-primary" onClick={download} disabled={!!busy}>
              <Download size={15} aria-hidden="true" /> {busy === "download" ? "Making the workbook…" : "Download Excel"}
            </button>
            <label className="btn btn-outline sdms-upload">
              <Upload size={15} aria-hidden="true" /> {busy === "checking" ? "Checking…" : "Upload filled Excel"}
              <input type="file" accept=".xlsx" hidden disabled={!!busy}
                     onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
            </label>
          </div>
        </div>
        <p className="lib-muted">1. Download Excel: every form with this session's answers. 2. Change the yellow Answer cells.
          3. Upload it: the changes are shown here and nothing is sent until you press Save. 4. Certify on the UDISE+ website.</p>
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
        {busy === "reading" && !data && <p className="lib-muted" role="status">Reading the forms from UDISE+…</p>}
      </div>

      {plan && (
        <div className="ui-panel">
          <h3 className="lib-section-title">Checked workbook</h3>
          <p><b>{plan.file_name}</b>, checked {when(plan.checked_at)}: <b>{plan.total_changes}</b> change{plan.total_changes === 1 ? "" : "s"} in{" "}
            {ready.length} form{ready.length === 1 ? "" : "s"} ready to save
            {plan.blocked_forms.length > 0 && <>; <b className="sdms-warn">{plan.blocked_forms.length}</b> form{plan.blocked_forms.length === 1 ? "" : "s"} with answers to correct first</>}.</p>
          {plan.forms.length === 0 && <p className="lib-muted">No answer differs from UDISE+.</p>}
          <ul className="sdms-plan-list">
            {plan.forms.map((f) => (
              <li key={f.key}>
                <details open={plan.forms.length <= 3 || f.problems.length > 0}>
                  <summary><b>{f.dcf}</b> {f.title} · {f.changes.length} change{f.changes.length === 1 ? "" : "s"}
                    {f.problems.length > 0 && <span className="sdms-warn"> · {f.problems.length} to correct</span>}
                    {f.certified && <span className="sdms-warn"> · certified (saving removes it)</span>}</summary>
                  {f.problems.length > 0 && (
                    <ul className="sdms-warn">{f.problems.map((p, i) => <li key={i}>{p.item} {p.question && `${p.question}: `}{p.message}</li>)}</ul>
                  )}
                  {f.changes.length > 0 && (
                    <table className="sdms-table sdms-fit">
                      <thead><tr><th>Item</th><th>Question</th><th>Now on UDISE+</th><th>After saving</th></tr></thead>
                      <tbody>{f.changes.map((c) => (
                        <tr key={c.id}><td>{c.item}</td><td>{c.question}{c.warning && <small className="sdms-warn"> {c.warning}</small>}</td>
                          <td>{c.old ?? "—"}</td><td><b>{c.new ?? "—"}</b></td></tr>))}
                      </tbody>
                    </table>
                  )}
                  {!f.problems.length && f.changes.some((c) => !c.warning) && (
                    <button type="button" className="btn btn-outline" disabled={!!busy} onClick={() => save([f.key])}>Save only this form</button>
                  )}
                </details>
              </li>
            ))}
          </ul>
          {ready.length > 0 && (
            <div className="sdms-actions">
              <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => save(null)}>
                {busy === "saving" ? "Saving to UDISE+…" : `Save ${ready.length} form${ready.length === 1 ? "" : "s"} to UDISE+`}
              </button>
            </div>
          )}
          {plan.results && (
            <table className="sdms-table sdms-fit" role="status">
              <thead><tr><th>Form</th><th>Result</th></tr></thead>
              <tbody>{plan.results.forms.map((r, i) => (
                <tr key={i}><td><b>{r.dcf}</b></td>
                  <td className={r.status === "saved" ? "" : "sdms-warn"}>
                    {r.status === "saved" && <CheckCircle2 size={14} aria-hidden="true" />} {STATUS[r.status]}
                    {r.saved !== undefined && ` (${r.saved} answer${r.saved === 1 ? "" : "s"})`}
                    {r.skipped && r.skipped.length > 0 && ` · left as on UDISE+: ${r.skipped.join(", ")}`}
                    {r.message && ` · ${r.message}`}</td></tr>))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {data && (
        <div className="ui-panel">
          <h3 className="lib-section-title">Forms for {data.year}</h3>
          <div className="sdms-scroll">
            <table className="sdms-table">
              <thead><tr><th>DCF items</th><th>Form</th><th>Answered</th><th>Still needed</th><th>Last saved on UDISE+</th><th>Certified</th></tr></thead>
              <tbody>{data.forms.map((f) => (
                <tr key={f.key}>
                  <td>{f.dcf}</td><td>{f.title}{f.error && <small className="sdms-warn"> {f.error}</small>}</td>
                  <td>{f.answered} of {f.questions}</td><td className={f.needed ? "sdms-warn" : ""}>{f.needed || "—"}</td>
                  <td>{f.modified ? f.modified.slice(0, 10) : "never"}</td>
                  <td>{f.certified ? "Yes" : "No"}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          {data.problems.length > 0 && (
            <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" />
              <div><b>Totals that do not add up on UDISE+:</b><ul>{data.problems.map((p, i) => <li key={i}>{p.dcf}: {p.message}</li>)}</ul></div></div>
          )}
          <details open={data.needed.length > 0 && data.needed.length <= 40}>
            <summary><b>Still needed: {data.needed.length}</b> question{data.needed.length === 1 ? "" : "s"} asked of the school and not answered on UDISE+</summary>
            {data.needed.length === 0 ? <p className="lib-muted">Every question asked of this school has an answer.</p> : (
              <div className="sdms-scroll"><table className="sdms-table sdms-fit">
                <thead><tr><th>DCF items</th><th>Item</th><th>Question</th><th>In the workbook</th><th>Allowed answers</th></tr></thead>
                <tbody>{data.needed.map((n, i) => (
                  <tr key={i}><td>{n.dcf}</td><td><b>{n.item}</b></td><td>{n.question}</td><td>sheet "{n.sheet}", row {n.row}</td><td>{n.allowed}</td></tr>))}
                </tbody></table></div>)}
          </details>
          <details>
            <summary><b>Updated from the app: {data.updated.length}</b> answer{data.updated.length === 1 ? "" : "s"} saved to UDISE+</summary>
            {data.updated.length === 0 ? <p className="lib-muted">Nothing has been saved from the app yet.</p> : (
              <div className="sdms-scroll"><table className="sdms-table sdms-fit">
                <thead><tr><th>When</th><th>DCF items</th><th>Item</th><th>Question</th><th>Before</th><th>After</th><th>Result</th></tr></thead>
                <tbody>{[...data.updated].reverse().map((u, i) => (
                  <tr key={i}><td>{when(u.at)}</td><td>{u.dcf}</td><td><b>{u.item}</b></td><td>{u.question}</td>
                    <td>{u.before ?? "—"}</td><td><b>{u.after ?? "—"}</b></td><td>{u.result}</td></tr>))}
                </tbody></table></div>)}
          </details>
          <p className="lib-muted">Not in the workbook (change them on the UDISE+ website): 1.1-1.30 basic details, 1.63 NSQF,
            the state's own questions, the sports list of 2.13 and 2.1(a).</p>
        </div>
      )}
    </div>
  );
}
