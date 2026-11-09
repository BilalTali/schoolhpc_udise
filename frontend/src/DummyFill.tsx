import { useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Shuffle } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";

// The school's dummy fill: days present and marks obtained at random inside a range, every student their own value,
// only where the School Register is EMPTY (what the school uploaded or typed stays). Check first, then fill.

interface Counts { students: number; months: number; marks: number }
interface Result extends Counts { applied: boolean; session: string; stages: Record<string, Counts>; notes: string[] }

const STAGES = ["Foundational", "Preparatory", "Middle"];

export function DummyFill({ api }: { api: Api }) {
  const [stage, setStage] = useState("");
  const [useDays, setUseDays] = useState(true);
  const [days, setDays] = useState({ low: "75", high: "95" });
  const [useMarks, setUseMarks] = useState(true);
  const [marks, setMarks] = useState({ low: "25", high: "45" });
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState<Result | null>(null);
  const [done, setDone] = useState<Result | null>(null);
  const [busy, setBusy] = useState<"" | "check" | "fill">("");
  const [error, setError] = useState<string | null>(null);

  const body = (apply: boolean) => ({
    stage: stage || null, apply, replace,
    attendance: useDays ? { low: Number(days.low), high: Number(days.high) } : null,
    marks: useMarks ? { low: Number(marks.low), high: Number(marks.high) } : null,
  });
  const reset = () => { setPreview(null); setDone(null); setError(null); };

  const run = async (apply: boolean) => {
    setError(null);
    if (apply && !window.confirm(`Fill ${preview?.months ?? 0} months of attendance and ${preview?.marks ?? 0} marks with dummy values `
      + `for ${preview?.students ?? 0} students? ` + (replace ? "What is there now is REPLACED." : "Only empty cells are filled."))) return;
    setBusy(apply ? "fill" : "check");
    try {
      const r = await call<Result>(api, "POST", "/school/register/data/dummy-fill", body(apply));
      if (apply) { setDone(r); setPreview(null); } else { setPreview(r); setDone(null); }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const range = (label: string, v: { low: string; high: string }, set: (v: { low: string; high: string }) => void,
                 on: boolean, unit: string) => (
    <div className="dummy-range">
      <label>{label} from <input type="number" className="form-input" min={0} value={v.low} disabled={!on}
               onChange={(e) => { set({ ...v, low: e.target.value }); reset(); }} aria-label={`${label}: lowest`} /></label>
      <label>to <input type="number" className="form-input" min={0} value={v.high} disabled={!on}
               onChange={(e) => { set({ ...v, high: e.target.value }); reset(); }} aria-label={`${label}: highest`} /> {unit}</label>
    </div>
  );
  const nothing = !useDays && !useMarks;
  const stageRows = (r: Result) => Object.entries(r.stages).map(([s, c]) => (
    <tr key={s}><td>{s}</td><td>{c.students}</td><td>{c.months}</td><td>{c.marks}</td></tr>));

  return (
    <div className="ui-panel dummy-fill">
      <div className="panel-header"><div className="panel-title"><Shuffle size={20} aria-hidden="true" /><span>Dummy attendance and marks</span></div></div>
      <p className="form-hint">Fills the School Register's <b>empty</b> days present and marks obtained at random inside the range you
        set - every student gets their own value. What you uploaded or typed is not changed unless you tick "Replace". Use it only when the real
        data is not available; the teachers' cards take these values like any other School Register data.</p>

      <div className="dummy-grid">
        <label className="reg-field"><span>Stage</span>
          <select className="reg-box" value={stage} onChange={(e) => { setStage(e.target.value); reset(); }}>
            <option value="">Every stage</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <div>
          <label className="aad-consent"><input type="checkbox" checked={useDays} onChange={(e) => { setUseDays(e.target.checked); reset(); }} /> Days present</label>
          {range("Days present", days, setDays, useDays, "% of each month's working days")}
        </div>
        <div>
          <label className="aad-consent"><input type="checkbox" checked={useMarks} onChange={(e) => { setUseMarks(e.target.checked); reset(); }} /> Summative marks</label>
          {range("Marks", marks, setMarks, useMarks, "marks (never above the subject's max marks, 50 by default)")}
        </div>
      </div>

      <label className="aad-consent">
        <input type="checkbox" checked={replace} onChange={(e) => { setReplace(e.target.checked); reset(); }} /> Replace what is
        already there (every cell gets a new value; a month without working days is emptied) - e.g. after a wrong upload
      </label>

      <div className="sdms-actions">
        <button type="button" className="btn btn-outline" disabled={!!busy || nothing} onClick={() => run(false)}>
          <RefreshCw size={15} className={busy === "check" ? "spin" : ""} aria-hidden="true" /> Check what would be filled
        </button>
        <button type="button" className="btn btn-primary" disabled={!!busy || !preview || !preview.students} onClick={() => run(true)}>
          <Shuffle size={15} aria-hidden="true" /> {busy === "fill" ? "Filling…" : "Fill now"}
        </button>
      </div>

      <div aria-live="polite">
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
        {(preview || done)?.notes.map((n) => <div key={n} className="alert-box alert-warning"><AlertCircle size={18} aria-hidden="true" /><div>{n}</div></div>)}
        {preview && (preview.students
          ? <>
              <p><b>{preview.students}</b> students {replace ? "get new values" : "have empty cells"}: <b>{preview.months}</b> months of attendance and <b>{preview.marks}</b> marks
                would be filled. Nothing is saved yet - press <b>Fill now</b>.</p>
              <table className="sdms-table sdms-fit"><thead><tr><th>Stage</th><th>Students</th><th>Months</th><th>Marks</th></tr></thead>
                <tbody>{stageRows(preview)}</tbody></table>
            </>
          : <p className="lib-muted">Nothing to fill: every cell in this range of the School Register already has a value.</p>)}
        {done && (
          <div className="alert-box alert-success">
            <CheckCircle2 size={18} aria-hidden="true" />
            <div>Filled <b>{done.months}</b> months of attendance and <b>{done.marks}</b> marks for <b>{done.students}</b> students
              (session {done.session.slice(0, 2)}-{done.session.slice(2)}).</div>
          </div>
        )}
      </div>
      {busy === "fill" && (
        <div className="mix-overlay" role="alertdialog" aria-modal="true" aria-label="Filling dummy values">
          <div className="mix-card">
            <RefreshCw size={40} className="spin mix-spinner" aria-hidden="true" />
            <h3>Filling dummy attendance and marks</h3>
            <p className="mix-wait"><b>Please wait.</b> Do not close or leave this page until this panel goes away.</p>
          </div>
        </div>
      )}
    </div>
  );
}
