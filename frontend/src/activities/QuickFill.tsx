import { useId, useState } from "react";
import { AlertCircle, CheckCircle2, Eye, Wand2 } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";
import { ABILITY_KEYS, ABILITY_LABEL, EACH_SUBJECT, LEVEL_VALUES, gradeOf } from "./gridTypes";
import type { AbilityKey, FillResult, GridData, LevelValue } from "./gridTypes";

// Fill many cells at once: every subject its own activity (for each student's grade), one activity, or only
// levels - for the whole class, one grade or the ticked students. Levels start at Proficient; "Mixed" deals
// Beginner / Proficient / Advanced out about equally (the apply writes exactly the mix its preview showed).
// Nothing changes until "Apply" after a preview; filled cells are kept unless the teacher says otherwise.

export function QuickFill({ api, stage, data, selectedIds, onApplied }: {
  api: Api;
  stage: string;
  data: GridData;
  selectedIds: string[];
  onApplied: (message: string) => void;
}) {
  // null: every subject its own activity (the default); "": levels only; otherwise one activity's key
  const [picked, setActivity] = useState<string | null>(null);
  const [subjectMode, setSubjectMode] = useState<"all" | "one">("all");
  const [subject, setSubject] = useState(data.subjects[0]?.code || "");
  const [who, setWho] = useState<"grade" | "ticked" | "pick">(selectedIds.length ? "ticked" : "grade");
  const [chosen, setChosen] = useState<Set<string>>(new Set());   // "Choose students": picked here, by name
  const [find, setFind] = useState("");
  const [grade, setGrade] = useState("");                         // "": every grade of the stage
  const [setLevels, setSetLevels] = useState(true);
  const [levels, setLevelsState] = useState<Partial<Record<AbilityKey, LevelValue | "Mixed">>>(
    { awareness: "Proficient", sensitivity: "Proficient", creativity: "Proficient" });
  const [replace, setReplace] = useState(false);
  const [replaceOld, setReplaceOld] = useState(false);            // tick 'Replace activities on PARAKH' too
  const [preview, setPreview] = useState<FillResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  // students being filled all in one grade: only that grade's activities (others are skipped by the server)
  const ids = who === "ticked" ? selectedIds : who === "pick" ? [...chosen] : null;
  const filling = ids ? data.students.filter((s) => ids.includes(s.student_id))
    : data.students.filter((s) => !grade || gradeOf(s) === grade);
  const gradeIds = new Set(filling.map((s) => s.grade_id));
  const gradeId = gradeIds.size === 1 ? [...gradeIds][0] : undefined;
  const offered = data.options.filter((o) => !o.subjects
    || ((subjectMode !== "one" || o.subjects.includes(subject)) && (gradeId == null || o.grade_id === gradeId)));
  // one activity always fits the grade and subject chosen: when they change, back to every subject's own
  const activity = picked === null || (picked && !offered.some((o) => o.key === picked)) ? EACH_SUBJECT : picked;
  const body = () => ({
    activity_key: activity,
    subjects: subjectMode === "one" ? [subject] : null,
    students: ids,
    grade: who === "grade" && grade ? grade : null,
    levels: setLevels ? levels : {},
    replace_filled: replace,
    replace_on_parakh: replaceOld,
  });
  const changed = () => setPreview(null);
  const shown = data.students.filter((s) => !find.trim() || s.student_name.toLowerCase().includes(find.trim().toLowerCase()));
  const chosenSubjects = (() => {                    // an activity is only filled in under its own subjects
    const subs = data.options.find((o) => o.key === activity)?.subjects;
    return subs ? data.subjects.filter((s) => subs.includes(s.code)).map((s) => s.name) : null;
  })();

  const run = async (apply: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const res = await call<FillResult>(api, "POST", `/teacher/activities-grid/${stage}/quick-fill`,
        { ...body(), apply, expected_cells: apply ? preview?.cells : undefined,
          mix_seed: apply ? preview?.mix_seed ?? undefined : undefined });
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

  const nothingToFill = !activity && !(setLevels && Object.keys(levels).length) && !replaceOld;
  const tickedNone = (who === "ticked" && selectedIds.length === 0) || (who === "pick" && chosen.size === 0);

  return (
    <section className="qf" aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`} className="lib-section-title"><Wand2 size={17} aria-hidden="true" /> Quick fill</h3>
      <div className="qf-grid">
        <label className="qf-field">
          <span className="lib-filter-label">Activity</span>
          <select className="form-select" value={activity} onChange={(e) => { setActivity(e.target.value); changed(); }}>
            <option value={EACH_SUBJECT}>Each subject's own activity</option>
            <option value="">— Only set levels —</option>
            {offered.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
          {activity === EACH_SUBJECT && (
            <span className="lib-muted">Every subject gets its own activity for each student's grade.</span>
          )}
          {chosenSubjects && (
            <span className="lib-muted">Goes only under its subject{chosenSubjects.length === 1 ? "" : "s"}: {chosenSubjects.join(", ")}</span>
          )}
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
                 onChange={() => { setWho("grade"); changed(); }} /> {data.grades.length > 1 ? "Whole class:" : `Whole class (${data.students.length})`}</label>
          {data.grades.length > 1 && (
            <select className="roster-filter-select" aria-label="Grade to fill" value={grade} disabled={who !== "grade"}
                    onChange={(e) => { setGrade(e.target.value); changed(); }}>
              <option value="">All grades ({data.students.length})</option>
              {data.grades.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
          <label className="lib-radio"><input type="radio" name={`${id}-who`} checked={who === "ticked"}
                 onChange={() => { setWho("ticked"); changed(); }} /> Only the {selectedIds.length} ticked</label>
          {/* changing a few students' levels: their levels are already filled, so they are replaced - and only
              the levels, so their chosen activities stay unless an activity is picked on purpose */}
          <label className="lib-radio"><input type="radio" name={`${id}-who`} checked={who === "pick"}
                 onChange={() => { setWho("pick"); setReplace(true); setActivity(""); changed(); }} /> Choose students{who === "pick" ? ` (${chosen.size})` : ""}</label>
        </fieldset>

        {who === "pick" && (
          <fieldset className="qf-field qf-fieldset qf-pick">
            <legend className="lib-filter-label">Students to change</legend>
            <input type="search" className="form-input qf-find" placeholder="Find a student" aria-label="Find a student"
                   value={find} onChange={(e) => setFind(e.target.value)} />
            <div className="qf-pick-actions">
              <button type="button" className="portal-link-btn"
                      onClick={() => { setChosen(new Set([...chosen, ...shown.map((s) => s.student_id)])); changed(); }}>Tick all shown</button>
              <button type="button" className="portal-link-btn" onClick={() => { setChosen(new Set()); changed(); }}>Clear</button>
            </div>
            <ul className="qf-pick-list">
              {shown.map((s) => (
                <li key={s.student_id}>
                  <label className="lib-radio">
                    <input type="checkbox" checked={chosen.has(s.student_id)} onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(s.student_id); else next.delete(s.student_id);
                      setChosen(next);
                      changed();
                    }} /> {s.student_name} <span className="lib-muted">{gradeOf(s)}</span>
                  </label>
                </li>
              ))}
              {!shown.length && <li className="lib-muted">No student matches.</li>}
            </ul>
          </fieldset>
        )}

        <fieldset className="qf-field qf-fieldset">
          <legend className="lib-filter-label">Filled cells</legend>
          <label className="lib-radio"><input type="radio" name={`${id}-rep`} checked={!replace}
                 onChange={() => { setReplace(false); changed(); }} /> Keep them</label>
          <label className="lib-radio"><input type="radio" name={`${id}-rep`} checked={replace}
                 onChange={() => { setReplace(true); changed(); }} /> Replace them</label>
          {/* older activities on PARAKH that the new choices no longer use are only removed when the teacher says so */}
          <label className="lib-radio qf-replace-old">
            <input type="checkbox" checked={replaceOld} onChange={(e) => { setReplaceOld(e.target.checked); changed(); }} />
            Replace older activities on PARAKH
          </label>
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
            {[...LEVEL_VALUES, "Mixed" as const].map((v) => (
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
        {tickedNone && <span className="lib-muted">{who === "pick" ? "Choose some students above first." : "Tick some students in the grid first."}</span>}
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
              {!!preview.no_activity?.length && <> No activity in your library for {preview.no_activity.join("; ")}: those cells stay empty.</>}
              {!!preview.older_on_parakh?.length && (
                <> <b>{preview.older_on_parakh.length}</b> student{preview.older_on_parakh.length === 1 ? " has" : "s have"} older
                  activities on PARAKH that the new choices no longer use ({preview.older_on_parakh.join(", ")}). Tick
                  <b> Replace older activities on PARAKH</b> to remove them when saving; until then those students are not ready.</>
              )}
              {preview.cells > 0 && <> Press <b>Apply</b> to fill them.</>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
