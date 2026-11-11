import { useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Wrench } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";

// After the class check: what keeps Part-B-complete students from being saved (the parent's name on the card,
// marks; days present when missing) filled in right here - into the School Register, only where it is empty.
// Names are typed; numbers come at random inside a range. Then the class is checked again.

export interface FixStudent {
  student_id: string;
  student_name?: string;
  grade: string;
  section: string;
  ready: boolean;
  other_problems: string[];
}

interface Result { names: number; months: number; marks: number; problems: string[] }

const needsName = (s: FixStudent) => s.other_problems.some((p) => p.includes("Guardian Name"));
const needsMarks = (s: FixStudent) => s.other_problems.some((p) => p.includes("marks obtained"));

export function FixMissing({ api, stage, students, onDone }: {
  api: Api; stage: string; students: FixStudent[]; onDone: () => Promise<void> | void;
}) {
  const nameless = useMemo(() => students.filter((s) => s.ready && needsName(s)), [students]);
  const markless = useMemo(() => students.filter((s) => s.ready && needsMarks(s)), [students]);
  const [names, setNames] = useState<Record<string, { relation: string; name: string }>>({});
  const [useMarks, setUseMarks] = useState(true);
  const [marks, setMarks] = useState({ low: "25", high: "45" });
  const [useDays, setUseDays] = useState(true);
  const [days, setDays] = useState({ low: "75", high: "95" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Result | null>(null);
  if (!nameless.length && !markless.length) return null;

  const row = (id: string) => names[id] || { relation: "Father", name: "" };
  const setRow = (id: string, v: Partial<{ relation: string; name: string }>) =>
    setNames((p) => ({ ...p, [id]: { ...row(id), ...v } }));
  const typed = Object.entries(names).filter(([, v]) => v.name.trim());

  const save = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const r = await call<Result>(api, "POST", `/teacher/template/${stage}/fill-missing`, {
        names: Object.fromEntries(typed),
        marks: markless.length && useMarks ? { low: Number(marks.low), high: Number(marks.high) } : null,
        attendance: useDays ? { low: Number(days.low), high: Number(days.high) } : null,
      });
      setDone(r);
      setNames({});
      await onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const range = (label: string, v: { low: string; high: string }, set: (v: { low: string; high: string }) => void,
                 on: boolean, unit: string) => (
    <span className="dummy-range">
      <label>from <input type="number" className="form-input" min={0} value={v.low} disabled={!on}
               onChange={(e) => set({ ...v, low: e.target.value })} aria-label={`${label}: lowest`} /></label>
      <label>to <input type="number" className="form-input" min={0} value={v.high} disabled={!on}
               onChange={(e) => set({ ...v, high: e.target.value })} aria-label={`${label}: highest`} /> {unit}</label>
    </span>
  );

  return (
    <div className="ui-panel fix-missing" aria-labelledby="fix-title">
      <h4 id="fix-title" className="lib-section-title"><Wrench size={16} aria-hidden="true" /> Fix what is missing</h4>
      <p className="lib-muted">Saved into the School Register, only where it is empty - nothing the school entered is changed.
        Then the class is checked again.</p>

      {nameless.length > 0 && (<>
        <b>Name on the HPC card ({nameless.length} student{nameless.length === 1 ? "" : "s"})</b>
        <div className="sdms-scroll"><table className="sdms-table sdms-fit">
          <thead><tr><th>Student</th><th>Whose name</th><th>Name</th></tr></thead>
          <tbody>{nameless.map((s) => (
            <tr key={s.student_id}>
              <td>{s.student_name || s.student_id} <small>{[s.grade, s.section].filter(Boolean).join(" ")}</small></td>
              <td><select className="reg-box" value={row(s.student_id).relation} aria-label={`Whose name for ${s.student_name}`}
                          onChange={(e) => setRow(s.student_id, { relation: e.target.value })}>
                {["Father", "Mother", "Guardian"].map((r) => <option key={r}>{r}</option>)}</select></td>
              <td className="sdms-long"><input className="form-input" maxLength={50} value={row(s.student_id).name}
                         placeholder="Letters, spaces, . ' -" aria-label={`Name for ${s.student_name}`}
                         onChange={(e) => setRow(s.student_id, { name: e.target.value })} /></td>
            </tr>))}
          </tbody></table></div>
      </>)}

      {markless.length > 0 && (
        <div className="fix-line">
          <label className="aad-consent"><input type="checkbox" checked={useMarks} onChange={(e) => setUseMarks(e.target.checked)} />
            {" "}Missing summative marks ({markless.length} student{markless.length === 1 ? "" : "s"}): each at random</label>
          {range("Marks", marks, setMarks, useMarks, "marks (never above the max)")}
        </div>)}
      <div className="fix-line">
        <label className="aad-consent"><input type="checkbox" checked={useDays} onChange={(e) => setUseDays(e.target.checked)} />
          {" "}Missing days present: each at random</label>
        {range("Days present", days, setDays, useDays, "% of the month's working days")}
      </div>

      <div className="sdms-actions">
        <button type="button" className="btn btn-primary" onClick={save}
                disabled={busy || (!typed.length && !(markless.length && useMarks) && !useDays)}>
          <Wrench size={15} aria-hidden="true" /> {busy ? "Saving and checking…" : "Save into the School Register and check again"}
        </button>
      </div>
      <div aria-live="polite">
        {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
        {done && (
          <div className="alert-box alert-success" role="status">
            <CheckCircle2 size={18} aria-hidden="true" />
            <div>Saved {done.names} name{done.names === 1 ? "" : "s"}, {done.marks} marks and {done.months} months of
              attendance.{done.problems.length > 0 && <> Not saved: {done.problems.join("; ")}.</>}</div>
          </div>)}
      </div>
    </div>
  );
}
