import { useId, useState } from "react";
import { AlertCircle, CheckCircle2, Eye, Wand2 } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";
import { ABILITY_KEYS, ABILITY_LABEL, LEVEL_VALUES } from "./gridTypes";
import type { AbilityKey, FillResult, GridData, LevelValue } from "./gridTypes";

// Fill many cells at once: one activity for the whole grade, for all subjects, or anything between.
// Nothing changes until "Apply" after a preview; filled cells are kept unless the teacher says otherwise.

export function QuickFill({ api, stage, data, selectedIds, onApplied }: {
  api: Api;
  stage: string;
  data: GridData;
  selectedIds: string[];
  onApplied: (message: string) => void;
}) {
  const [activity, setActivity] = useState(data.options[0]?.key || "");
  const [subjectMode, setSubjectMode] = useState<"all" | "one">("all");
  const [subject, setSubject] = useState(data.subjects[0]?.code || "");
  const [who, setWho] = useState<"grade" | "ticked">(selectedIds.length ? "ticked" : "grade");
  const [grade, setGrade] = useState(data.grades[0] || "");
  const [setLevels, setSetLevels] = useState(false);
  const [levels, setLevelsState] = useState<Partial<Record<AbilityKey, LevelValue>>>({});
  const [replace, setReplace] = useState(false);
  const [preview, setPreview] = useState<FillResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  const body = () => ({
    activity_key: activity,
    subjects: subjectMode === "one" ? [subject] : null,
    students: who === "ticked" ? selectedIds : null,
    grade: who === "grade" && data.grades.length > 1 ? grade : null,
    levels: setLevels ? levels : {},
    replace_filled: replace,
  });
  const changed = () => setPreview(null);

  const run = async (apply: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const res = await call<FillResult>(api, "POST", `/teacher/activities-grid/${stage}/quick-fill`,
        { ...body(), apply, expected_cells: apply ? preview?.cells : undefined });
      if (apply) {
        setPreview(null);
        onApplied(`Filled ${res.cells} cell${res.cells === 1 ? "" : "s"} for ${res.students} student${res.students === 1 ? "" : "s"}.`);
      } else {
        setPreview(res);
      }
    } catch (e: any) {
      setError(e.message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const nothingToFill = !activity && !(setLevels && Object.keys(levels).length);
  const tickedNone = who === "ticked" && selectedIds.length === 0;

  return (
    <section className="qf" aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`} className="lib-section-title"><Wand2 size={17} aria-hidden="true" /> Quick fill</h3>
      <div className="qf-grid">
        <label className="qf-field">
          <span className="lib-filter-label">Activity</span>
          <select className="form-select" value={activity} onChange={(e) => { setActivity(e.target.value); changed(); }}>
            <option value="">— Only set levels —</option>
            {data.options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </label>

        <fieldset className="qf-field qf-fieldset">
          <legend className="lib-filter-label">Subjects</legend>
          <label className="lib-radio"><input type="radio" name={`${id}-subj`} checked={subjectMode === "all"}
                 onChange={() => { setSubjectMode("all"); changed(); }} /> All subjects</label>
          <label className="lib-radio"><input type="radio" name={`${id}-subj`} checked={subjectMode === "one"}
                 onChange={() => { setSubjectMode("one"); changed(); }} /> Only:</label>
          <select className="roster-filter-select" aria-label="Subject to fill" value={subject} disabled={subjectMode !== "one"}
                  onChange={(e) => { setSubject(e.target.value); changed(); }}>
            {data.subjects.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
        </fieldset>

        <fieldset className="qf-field qf-fieldset">
          <legend className="lib-filter-label">Students</legend>
          <label className="lib-radio"><input type="radio" name={`${id}-who`} checked={who === "grade"}
                 onChange={() => { setWho("grade"); changed(); }} /> {data.grades.length > 1 ? "Whole grade:" : `Whole class (${data.students.length})`}</label>
          {data.grades.length > 1 && (
            <select className="roster-filter-select" aria-label="Grade to fill" value={grade} disabled={who !== "grade"}
                    onChange={(e) => { setGrade(e.target.value); changed(); }}>
              {data.grades.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
          <label className="lib-radio"><input type="radio" name={`${id}-who`} checked={who === "ticked"}
                 onChange={() => { setWho("ticked"); changed(); }} /> Only the {selectedIds.length} ticked</label>
        </fieldset>

        <fieldset className="qf-field qf-fieldset">
          <legend className="lib-filter-label">Filled cells</legend>
          <label className="lib-radio"><input type="radio" name={`${id}-rep`} checked={!replace}
                 onChange={() => { setReplace(false); changed(); }} /> Keep them</label>
          <label className="lib-radio"><input type="radio" name={`${id}-rep`} checked={replace}
                 onChange={() => { setReplace(true); changed(); }} /> Replace them</label>
        </fieldset>
      </div>

      <fieldset className="qf-levels">
        <legend className="lib-filter-label">Levels</legend>
        <label className="lib-radio"><input type="radio" name={`${id}-lv`} checked={!setLevels}
               onChange={() => { setSetLevels(false); changed(); }} /> Leave them as they are</label>
        <label className="lib-radio"><input type="radio" name={`${id}-lv`} checked={setLevels}
               onChange={() => { setSetLevels(true); changed(); }} /> Also set:</label>
        {setLevels && ABILITY_KEYS.map((a) => (
          <div key={a} className="qf-level" role="radiogroup" aria-label={`${ABILITY_LABEL[a]} level to fill`}>
            <span>{ABILITY_LABEL[a]}</span>
            {LEVEL_VALUES.map((v) => (
              <label key={v} className="qf-level-opt">
                <input type="radio" name={`${id}-lv-${a}`} checked={levels[a] === v}
                       onChange={() => { setLevelsState((l) => ({ ...l, [a]: v })); changed(); }} />{v}
              </label>
            ))}
          </div>
        ))}
      </fieldset>

      <div className="qf-actions">
        <button type="button" className="btn btn-outline" onClick={() => run(false)} disabled={busy || nothingToFill || tickedNone}>
          <Eye size={15} aria-hidden="true" /> Preview
        </button>
        <button type="button" className="btn btn-green" onClick={() => run(true)} disabled={busy || !preview || preview.cells === 0}>
          Apply
        </button>
        {tickedNone && <span className="lib-muted">Tick some students in the grid first.</span>}
      </div>

      <div aria-live="polite">
        {error && <div className="alert-box alert-error lib-inline-alert" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
        {preview && (
          <div className="alert-box alert-info lib-inline-alert">
            <CheckCircle2 size={18} aria-hidden="true" />
            <div>
              {preview.cells === 0
                ? "Nothing to fill: every cell already has a value."
                : <>Fills <b>{preview.cells}</b> cell{preview.cells === 1 ? "" : "s"} for <b>{preview.students}</b> student{preview.students === 1 ? "" : "s"} ({preview.subjects.length === data.subjects.length ? "all subjects" : preview.subjects.join(", ")}).</>}
              {preview.kept > 0 && <> Keeps {preview.kept} cell{preview.kept === 1 ? "" : "s"} that already have a value.</>}
              {preview.skipped.length > 0 && <> Skips {preview.skipped.map((s) => s.student_name).join(", ")}: {preview.skipped[0].reason}</>}
              {preview.cells > 0 && <> Press <b>Apply</b> to fill them.</>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
