import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Download, RefreshCw, Upload } from "lucide-react";
import { ApiError, apiFetch, call } from "./api";
import type { Api } from "./api";
import { downloadSheet } from "./downloadSheet";

// APAAR from the consent sheet: download (the students ready) -> fill each parent's physical consent -> upload
// (checked here, nothing sent) -> generate one first, or all, after confirming. A row without "Yes" in
// "Consent signed" is left out; a student is never generated twice.

interface Row { row: number; pen: string; name: string; class?: string; problems: string[]; already: string | null }
interface Plan { file_name: string; rows: Row[]; ready: number; with_problems: number; already: number }
interface Result { row: number; name: string; class: string; apaar_id: string | null; error: string | null }
interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; results: Result[]; error: string | null }

export function ApaarSheet({ api, ready, onDone }: { api: Api; ready: number; onDone: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [first, setFirst] = useState<number | "">("");

  const look = useCallback(async () => {
    try {
      const r = await call<{ plan: Plan | null; job: Job | null }>(api, "GET", "/school/udise/sdms/apaar/consent");
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
      if (j && j.status !== "RUNNING") onDone();
    }, 2000);
    return () => window.clearTimeout(t);
  }, [running, job, look, onDone]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch("/school/udise/sdms/apaar/consent/validate", { method: "POST", body: form }, api.base);
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

  const generate = async (rows: number[] | null) => {
    const who = rows ? plan?.rows.find((r) => r.row === rows[0])?.name : `${plan?.ready} students`;
    if (!window.confirm(`Generate the APAAR ID for ${who} on SDMS now, with the consents in the sheet?`)) return;
    setBusy(true);
    setError(null);
    try {
      await call(api, "POST", "/school/udise/sdms/apaar/consent/generate", { confirm: true, rows });
      await look();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ok = (plan?.rows || []).filter((r) => !r.problems.length && !r.already);
  return (
    <div className="sdms-admit">
      <div className="sdms-actions">
        <button type="button" className="btn btn-outline" disabled={!ready}
                onClick={async () => setError(await downloadSheet(api, "/school/udise/sdms/apaar/consent.xlsx", "APAAR_consent.xlsx"))}>
          <Download size={15} aria-hidden="true" /> Consent sheet ({ready} ready)
        </button>
        <label className="btn btn-outline sdms-upload">
          <Upload size={15} aria-hidden="true" /> {busy && !running ? "Checking…" : "Upload the filled consent sheet"}
          <input type="file" accept=".xlsx" hidden disabled={busy || running}
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </label>
      </div>
      <p className="lib-muted">Fill one row per student whose father, mother or legal guardian signed the physical consent, and write
        "Yes" in "Consent signed". Rows without it are left out.</p>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}

      {plan && !running && (
        <div className="sdms-plan">
          <p><b>{plan.file_name}</b>: <b>{plan.ready}</b> ready to generate
            {plan.with_problems > 0 && <>, <b className="sdms-warn">{plan.with_problems}</b> to correct</>}
            {plan.already > 0 && <>, {plan.already} have an APAAR ID already</>}.</p>
          <ul className="sdms-plan-list">
            {plan.rows.map((r) => (
              <li key={r.row}><b>{r.name}</b> · {r.class} · row {r.row}
                {r.already ? <span> · <CheckCircle2 size={13} aria-hidden="true" /> APAAR ID {r.already}</span>
                  : r.problems.length ? <p className="sdms-warn">Correct in the sheet: {r.problems.join("; ")}</p>
                  : <span className="lib-muted"> · ready</span>}
              </li>
            ))}
          </ul>
          {ok.length > 0 && (
            <div className="sdms-actions">
              <select className="form-input" value={first} onChange={(e) => setFirst(e.target.value ? Number(e.target.value) : "")}
                      aria-label="The student to generate first">
                <option value="">Choose one student to generate first…</option>
                {ok.map((r) => <option key={r.row} value={r.row}>{r.name} ({r.class})</option>)}
              </select>
              <button type="button" className="btn btn-outline" disabled={busy || first === ""} onClick={() => generate([first as number])}>
                Generate this one
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => generate(null)}>Generate all {plan.ready}</button>
            </div>
          )}
        </div>
      )}

      {job && (
        <div className="sdms-progress" role="status">
          {running && <div><RefreshCw size={14} className="spin" aria-hidden="true" /> <b>Generating APAAR IDs…</b> {job.done} of {job.total}</div>}
          {job.status === "FAILED" && job.error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
          {job.results.length > 0 && (
            <table className="sdms-table sdms-fit">
              <thead><tr><th>Student</th><th>APAAR ID</th><th>Result</th></tr></thead>
              <tbody>
                {job.results.map((r) => (
                  <tr key={r.row}>
                    <td><b>{r.name}</b><small>{r.class} · row {r.row}</small></td>
                    <td>{r.apaar_id || "—"}</td>
                    <td className={r.error ? "sdms-warn" : ""}>{r.error || <><CheckCircle2 size={14} aria-hidden="true" /> Generated on SDMS</>}</td>
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
