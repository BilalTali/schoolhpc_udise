import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Clock, FileUp, Lock, RefreshCw, Search } from "lucide-react";
import { ApiError, call } from "../api";
import type { Api } from "../api";
import { QuickFill } from "./QuickFill";
import { useCardCheck } from "./useCardCheck";
import { ConnectPrompt } from "./ConnectPrompt";
import { needsParakh } from "./parakhConnect";
import { ABILITY_KEYS, ABILITY_LABEL, LEVEL_VALUES, REPLACE_KEY, actKey, gradeOf, levelKey } from "./gridTypes";
import type { GridData, GridStudent } from "./gridTypes";

// The Activities tab: every fetched student in rows; per subject an activity and three levels.
// Every change is saved (as a draft) about a second later. Nothing goes to PARAKH from here.

type SaveState = "saving" | "saved" | "error" | "conflict" | undefined;
const SAVE_DELAY = 800;
const SHORT: Record<string, string> = { Beginner: "B", Proficient: "P", Advanced: "A" };

export function ActivitiesGrid({ api, stage, uploadedFile, focusStudent, libraryHref }: {
  api: Api; stage: string; uploadedFile?: string;
  focusStudent?: string;                          // opened and scrolled to (from "Fix in Activities")
  libraryHref?: string;                           // the Activity Library, where activities are edited or added
}) {
  const [data, setData] = useState<GridData | null>(null);
  const [rows, setRows] = useState<Record<string, GridStudent>>({});
  const [offline, setOffline] = useState(false);              // PARAKH not connected
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<Record<string, SaveState>>({});
  const [shown, setShown] = useState<string[] | null>(null);       // subject codes on screen (null = all)
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [gradeFilter, setGradeFilter] = useState("");
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(focusStudent ?? null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [showFill, setShowFill] = useState(true);

  const pending = useRef<Record<string, Record<string, string>>>({});
  const timers = useRef<Record<string, number>>({});
  const versions = useRef<Record<string, number>>({});
  const alive = useRef(true);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const d = await call<GridData>(api, "GET", `/teacher/activities-grid/${stage}${refresh ? "?refresh=true" : ""}`);
      if (!alive.current) return;
      setData(d);
      setRows(Object.fromEntries(d.students.map((s) => [s.student_id, s])));
      versions.current = Object.fromEntries(d.students.map((s) => [s.student_id, s.draft_version]));
    } catch (e: any) {
      if (alive.current) { setError(e.message); setOffline(needsParakh(e)); }
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [api, stage]);

  useEffect(() => {
    alive.current = true;
    load();
  }, [load]);

  const checking = useCardCheck(api, stage, !!data, (ids) => {
    const waiting = Object.keys(pending.current).length > 0;
    const text = `${ids.length} student${ids.length === 1 ? "'s card was" : "s' cards were"} changed on PARAKH since your copy.`;
    if (waiting) setMessage({ type: "error", text: `${text} Your changes are still being saved; press "Read again from PARAKH" afterwards to see them.` });
    else load().then(() => setMessage({ type: "success", text: `Updated from PARAKH: ${text}` }));
  });

  const flush = useCallback(async (sid: string) => {
    const values = pending.current[sid];
    if (!values) return;
    delete pending.current[sid];
    setSaveState((s) => ({ ...s, [sid]: "saving" }));
    try {
      const row = await call<GridStudent>(api, "PUT", `/teacher/activities-grid/${stage}/${sid}`,
                                          { values, base_version: versions.current[sid] ?? 0 });
      if (!alive.current) return;
      versions.current[sid] = row.draft_version;
      // keep anything typed while this save was on its way
      setRows((r) => ({ ...r, [sid]: { ...row, values: { ...row.values, ...(pending.current[sid] || {}) } } }));
      setSaveState((s) => ({ ...s, [sid]: pending.current[sid] ? "saving" : "saved" }));
    } catch (e: any) {
      if (!alive.current) return;
      pending.current[sid] = { ...values, ...(pending.current[sid] || {}) };
      setSaveState((s) => ({ ...s, [sid]: e instanceof ApiError && e.status === 409 ? "conflict" : "error" }));
      if (!(e instanceof ApiError && e.status === 409)) setMessage({ type: "error", text: e.message });
    }
  }, [api, stage]);

  // Leaving the tab or switching stage sends any change still waiting, instead of dropping it.
  const flushRef = useRef(flush);
  useEffect(() => { flushRef.current = flush; });
  useEffect(() => {
    const t = timers.current;
    const waiting = pending.current;
    return () => {
      alive.current = false;
      Object.values(t).forEach((x) => window.clearTimeout(x));
      Object.keys(waiting).forEach((sid) => flushRef.current(sid));
    };
  }, []);

  const change = useCallback((sid: string, key: string, value: string) => {
    setRows((r) => {
      const row = r[sid];
      return { ...r, [sid]: { ...row, values: { ...row.values, [key]: value }, source: { ...row.source, [key]: "draft" } } };
    });
    pending.current[sid] = { ...(pending.current[sid] || {}), [key]: value };
    setSaveState((s) => ({ ...s, [sid]: "saving" }));
    window.clearTimeout(timers.current[sid]);
    timers.current[sid] = window.setTimeout(() => flush(sid), SAVE_DELAY);
  }, [flush]);

  // Read through refs so the callbacks stay the same and unchanged rows are not drawn again.
  const rowsRef = useRef(rows);
  const dataRef = useRef(data);
  useEffect(() => { rowsRef.current = rows; dataRef.current = data; });
  const sameForAll = useCallback((sid: string) => {
    const row = rowsRef.current[sid];
    const data = dataRef.current;
    if (!row || !data) return;
    const first = data.subjects.find((s) => row.values[actKey(s.code)]);
    if (!first) return;
    for (const s of data.subjects) {
      change(sid, actKey(s.code), row.values[actKey(first.code)]);
      for (const a of ABILITY_KEYS) if (row.values[levelKey(first.code, a)]) change(sid, levelKey(s.code, a), row.values[levelKey(first.code, a)]);
    }
  }, [change]);
  const expand = useCallback((sid: string) => setExpanded((x) => (x === sid ? null : sid)), []);
  const reload = useCallback(() => { load(); }, [load]);

  // Warn before closing the tab while a save is waiting.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (Object.keys(pending.current).length) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const subjects = useMemo(() => (data?.subjects || []).filter((s) => !shown || shown.includes(s.code)), [data, shown]);
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return Object.values(rows).filter((r) =>
      (!q || r.student_name.toLowerCase().includes(q)) && (!gradeFilter || gradeOf(r) === gradeFilter) && (!onlyProblems || !r.ready));
  }, [rows, search, gradeFilter, onlyProblems]);
  const order = useMemo(() => (data?.students || []).map((s) => s.student_id), [data]);
  const loaded = !!data;
  useEffect(() => {
    if (loaded && focusStudent) document.getElementById(`grid-row-${focusStudent}`)?.scrollIntoView?.({ block: "center" });
  }, [loaded, focusStudent]);
  const visibleSorted = useMemo(() => {
    const ids = new Set(visible.map((r) => r.student_id));
    return order.filter((id) => ids.has(id)).map((id) => rows[id]);
  }, [visible, order, rows]);

  const ready = Object.values(rows).filter((r) => r.ready).length;
  const allTicked = visibleSorted.length > 0 && visibleSorted.every((r) => selected.has(r.student_id));
  const toggle = useCallback((sid: string) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(sid)) n.delete(sid); else n.add(sid);
    return n;
  }), []);

  if (error && !data && offline) {
    return <div className="ui-panel"><ConnectPrompt what="your class's activities" /></div>;
  }
  if (error && !data) {
    return (
      <div className="ui-panel">
        <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" />
          <div>{error} <button type="button" className="portal-link-btn" onClick={() => load()}>Try again</button></div></div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="ui-panel">
        <div className="lib-skeleton" aria-busy="true" aria-label="Loading students and their activities">
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="lib-skeleton-row"><span /><span /><span /></div>)}
        </div>
        <p className="lib-muted">Reading each student's activities from PARAKH… this takes a few seconds the first time.</p>
      </div>
    );
  }

  return (
    <div className="ui-panel grid-panel">
      <div className="panel-header">
        <div className="panel-title"><CheckCircle2 size={20} color="#046A38" aria-hidden="true" /><span>Activities and levels – {stage}</span></div>
        <div className="grid-head-actions">
          <span className="grid-ready" role="status"><b>{ready}</b> of {Object.keys(rows).length} students ready</span>
          <button type="button" className="btn btn-outline" onClick={() => load(true)} disabled={loading}>
            <RefreshCw size={14} aria-hidden="true" className={loading ? "spin" : ""} /> Read again from PARAKH
          </button>
        </div>
      </div>
      {checking && <p className="lib-muted" aria-live="polite">Checking PARAKH for changes… ({checking.done} of {checking.total})</p>}
      <p className="lib-muted">Choose an activity and the three levels for each subject. Changes are saved automatically and go into your Excel download. They reach PARAKH when you submit the card or upload the Excel file.
        {libraryHref && <> To change an activity's texts and questions, or add your own, open the <Link to={libraryHref}>Activity Library</Link>.</>}</p>

      <div aria-live="polite">
        {message && (
          <div className={`alert-box alert-${message.type} lib-inline-alert`}>
            {message.type === "error" ? <AlertCircle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
            <div style={{ flex: 1 }}>{message.text}</div>
            <button type="button" className="portal-link-btn" onClick={() => setMessage(null)}>Dismiss</button>
          </div>
        )}
      </div>

      <button type="button" className="portal-link-btn grid-fill-toggle" aria-expanded={showFill} onClick={() => setShowFill(!showFill)}>
        {showFill ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />} Quick fill
      </button>
      {showFill && (
        <QuickFill api={api} stage={stage} data={data} selectedIds={[...selected]}
                   onApplied={(text) => { setMessage({ type: "success", text }); load(); }} />
      )}
      {uploadedFile && <ImportFromFile api={api} stage={stage} fileName={uploadedFile} onApplied={(t) => { setMessage({ type: "success", text: t }); load(); }} />}

      <div className="grid-tools">
        <div className="roster-search-input">
          <Search size={16} aria-hidden="true" />
          <label htmlFor="grid-search" className="sr-only">Search students</label>
          <input id="grid-search" type="search" placeholder="Search student name" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {data.grades.length > 1 && (
          <div className="lib-filter">
            <label htmlFor="grid-grade" className="lib-filter-label">Grade</label>
            <select id="grid-grade" className="roster-filter-select" value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)}>
              <option value="">All grades</option>
              {data.grades.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
        )}
        <label className="lib-check"><input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} /> Only students that need work</label>
        <details className="grid-subjects">
          <summary>Show subjects ({subjects.length} of {data.subjects.length})</summary>
          <div className="grid-subjects-list">
            <button type="button" className="portal-link-btn" onClick={() => setShown(null)}>All</button>
            {data.subjects.map((s) => (
              <label key={s.code} className="lib-check">
                <input type="checkbox" checked={!shown || shown.includes(s.code)}
                       onChange={(e) => {
                         const now = shown || data.subjects.map((x) => x.code);
                         const next = e.target.checked ? [...now, s.code] : now.filter((c) => c !== s.code);
                         setShown(next.length ? data.subjects.map((x) => x.code).filter((c) => next.includes(c)) : now);
                       }} /> {s.name}
              </label>
            ))}
          </div>
        </details>
      </div>

      {Object.keys(rows).length === 0 ? (
        <div className="empty-roster-box"><h2 className="lib-empty-title">No students</h2><p className="lib-muted">Fetch your class from PARAKH on the roster tab first.</p></div>
      ) : (
        <div className="grid-scroll" role="region" aria-label="Activities grid" tabIndex={0}>
          <table className="grid-table">
            <caption className="sr-only">Activities and levels for each student and subject. Levels: B is Beginner, P is Proficient, A is Advanced.</caption>
            <thead>
              <tr>
                <th scope="col" rowSpan={2} className="grid-sticky grid-student-head">
                  <input type="checkbox" checked={allTicked} aria-label="Tick all students shown"
                         onChange={() => setSelected(allTicked ? new Set() : new Set(visibleSorted.map((r) => r.student_id)))} />
                  <span>Student</span>
                </th>
                <th scope="col" rowSpan={2} className="grid-status-head">Status</th>
                {subjects.map((s) => <th key={s.code} scope="colgroup" colSpan={4} className="grid-subject-head">{s.name}</th>)}
              </tr>
              <tr>
                {subjects.map((s) => <SubHead key={s.code} />)}
              </tr>
            </thead>
            <tbody>
              {visibleSorted.map((r) => (
                <GridRow key={r.student_id} row={r} subjects={subjects} options={data.options} labels={data.labels}
                         ticked={selected.has(r.student_id)} save={saveState[r.student_id]} expanded={expanded === r.student_id}
                         onToggle={toggle} onChange={change} onExpand={expand}
                         onSameForAll={sameForAll} onReload={reload} />
              ))}
            </tbody>
          </table>
          {visibleSorted.length === 0 && <p className="lib-muted grid-none">No students match. <button type="button" className="portal-link-btn" onClick={() => { setSearch(""); setGradeFilter(""); setOnlyProblems(false); }}>Show everyone</button></p>}
        </div>
      )}
    </div>
  );
}

function SubHead() {
  return (
    <>
      <th scope="col" className="grid-act-head">Activity</th>
      {ABILITY_KEYS.map((a) => (
        <th key={a} scope="col" className="grid-level-head">
          {ABILITY_LABEL[a]}
          <span className="grid-bpa" aria-hidden="true"><span>B</span><span>P</span><span>A</span></span>
        </th>
      ))}
    </>
  );
}

interface RowProps {
  row: GridStudent;
  subjects: { code: string; name: string }[];
  options: { key: string; label: string }[];
  labels: Record<string, string>;
  ticked: boolean;
  save: SaveState;
  expanded: boolean;
  onToggle: (sid: string) => void;
  onChange: (sid: string, key: string, value: string) => void;
  onExpand: (sid: string) => void;
  onSameForAll: (sid: string) => void;
  onReload: () => void;
}

const GridRow = memo(function GridRow({ row, subjects, options, labels, ticked, save, expanded, onToggle, onChange, onExpand, onSameForAll, onReload }: RowProps) {
  const sid = row.student_id;
  const lockedOut = row.locked && !row.replace;
  const optionKeys = useMemo(() => new Set(options.map((o) => o.key)), [options]);
  const span = 2 + subjects.length * 4;
  return (
    <>
      <tr id={`grid-row-${sid}`} className={`${row.ready ? "" : "grid-row-todo"} ${lockedOut ? "grid-row-locked" : ""}`}>
        <th scope="row" className="grid-sticky grid-student">
          <input type="checkbox" checked={ticked} onChange={() => onToggle(sid)} aria-label={`Tick ${row.student_name}`} />
          <span className="grid-name">
            <b>{row.student_name}</b>
            <small>{[row.grade, row.section && `Sec ${row.section}`].filter(Boolean).join(" · ")}</small>
          </span>
        </th>
        <td className="grid-status">
          {row.ready
            ? <span className="lib-badge lib-badge-ok"><CheckCircle2 size={12} aria-hidden="true" /> Ready</span>
            : <span className="lib-badge lib-badge-warn"><AlertCircle size={12} aria-hidden="true" /> Needs work</span>}
          {row.locked && (
            <button type="button" className="lib-badge" onClick={() => { if (!expanded) onExpand(sid); }}
                    title="PARAKH has more than one activity for a subject. Open the details and tick 'Replace activities on PARAKH' to edit.">
              <Lock size={11} aria-hidden="true" /> {row.replace ? "Unlocked: will replace" : "Locked – click to edit"}
            </button>
          )}
          <SaveBadge state={save} onReload={onReload} />
          <button type="button" className="portal-link-btn" aria-expanded={expanded} onClick={() => onExpand(sid)}>
            {expanded ? "Hide details" : "Details"}<span className="sr-only"> for {row.student_name}</span>
          </button>
        </td>
        {subjects.map((s) => {
          const value = row.values[actKey(s.code)] || "";
          const unknown = value && !optionKeys.has(value);
          return (
            <Cells key={s.code} sid={sid} name={row.student_name} subject={s} value={value} row={row}
                   options={options} unknownLabel={unknown ? labels[value] || value : ""} disabled={lockedOut} onChange={onChange} />
          );
        })}
      </tr>
      {expanded && (
        <tr className="grid-detail-row">
          <td colSpan={span}>
            <div className="grid-detail">
              {row.problems.length > 0 && (
                <div><b>To fix before saving to PARAKH:</b><ul>{row.problems.map((p) => <li key={p}>{p}</li>)}</ul></div>
              )}
              {row.notes.length > 0 && <div><b>What a save would do:</b><ul>{row.notes.map((n) => <li key={n}>{n}</li>)}</ul></div>}
              <div>
                <b>On PARAKH now:</b>{" "}
                {row.existing.length === 0 ? "no activities yet." : (
                  <ul>{row.existing.map((e, i) => (
                    <li key={i}>{e.label || e.name}{e.subject_names.length ? ` – ${e.subject_names.join(", ")}` : ""}{e.complete ? "" : " (not finished)"}</li>
                  ))}</ul>
                )}
              </div>
              <div className="grid-detail-actions">
                <button type="button" className="btn btn-outline" onClick={() => onSameForAll(sid)} disabled={lockedOut}>
                  Use the first subject's activity and levels for all subjects
                </button>
                {(row.locked || row.existing.length > 0) && (
                  <label className="lib-check">
                    <input type="checkbox" checked={row.replace} onChange={(e) => onChange(sid, REPLACE_KEY, e.target.checked ? "Yes" : "")} />
                    Replace activities on PARAKH with the ones chosen here
                    {row.locked && !row.replace && <span className="lib-muted"> (tick this to edit: PARAKH has more than one activity for a subject)</span>}
                  </label>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
});

function Cells({ sid, name, subject, value, row, options, unknownLabel, disabled, onChange }: {
  sid: string; name: string; subject: { code: string; name: string }; value: string; row: GridStudent;
  options: { key: string; label: string; subjects?: string[] | null; grade?: string }[]; unknownLabel: string; disabled: boolean;
  onChange: (sid: string, key: string, value: string) => void;
}) {
  const ak = actKey(subject.code);
  // only this subject's activities (R1 under R1, Mathematics under Mathematics), and of them the ones for the
  // student's grade; when PARAKH has none for the grade or the subject, a wider list with a remark saying so.
  // A choice made before that belongs elsewhere stays visible, marked, so nothing disappears silently.
  const own = options.filter((o) => !o.subjects || o.subjects.includes(subject.code));
  const forGrade = row.grade ? own.filter((o) => !o.grade || o.grade === row.grade) : own;
  const mine = forGrade.length ? forGrade : own.length ? own : options;
  const remark = !own.length ? `No ${subject.name} activity on PARAKH - showing every activity`
    : !forGrade.length ? `No ${subject.name} activity for ${row.grade} on PARAKH - showing other grades` : "";
  const elsewhere = value && !mine.some((o) => o.key === value) ? options.find((o) => o.key === value) : undefined;
  return (
    <>
      <td className={`grid-act ${value ? "" : "grid-empty"} ${row.source[ak] === "default" ? "grid-from-c" : ""}`}
          title={row.source[ak] === "default" ? "Filled in: this subject's own activity. Choose another to change it." : undefined}>
        <select value={value} disabled={disabled} aria-label={`${name}, ${subject.name}, activity`}
                onChange={(e) => onChange(sid, ak, e.target.value)}>
          <option value="">— Choose —</option>
          {unknownLabel && <option value={value}>{unknownLabel} (kept from PARAKH)</option>}
          {elsewhere && <option value={elsewhere.key}>{elsewhere.label} (not for this subject)</option>}
          {mine.map((o) => <option key={o.key} value={o.key}>{o.label}{forGrade.length || !o.grade ? "" : ` (${o.grade})`}</option>)}
        </select>
        {remark && <small className="grid-note" title={remark}>{!own.length ? "All activities" : "Other grades"}</small>}
      </td>
      {ABILITY_KEYS.map((a) => {
        const k = levelKey(subject.code, a);
        const current = row.values[k] || "";
        const fromC = row.source[k] === "part_c";
        return (
          <td key={a} className={`grid-level ${current ? "" : "grid-empty"} ${fromC ? "grid-from-c" : ""}`}>
            <div role="radiogroup" aria-label={`${name}, ${subject.name}, ${ABILITY_LABEL[a]}${fromC ? " (taken from Part C)" : ""}`} className="grid-radios">
              {LEVEL_VALUES.map((v) => (
                <label key={v} className="grid-radio" title={v}>
                  <input type="radio" name={`${sid}-${subject.code}-${a}`} value={v} checked={current === v} disabled={disabled}
                         onChange={() => onChange(sid, k, v)} />
                  <span aria-hidden="true">{SHORT[v]}</span>
                  <span className="sr-only">{v}</span>
                </label>
              ))}
            </div>
          </td>
        );
      })}
    </>
  );
}

function SaveBadge({ state, onReload }: { state: SaveState; onReload: () => void }) {
  if (state === "saving") return <span className="grid-save"><Clock size={11} aria-hidden="true" /> Saving…</span>;
  if (state === "saved") return <span className="grid-save grid-save-ok"><CheckCircle2 size={11} aria-hidden="true" /> Saved</span>;
  if (state === "error") return <span className="grid-save grid-save-bad"><AlertCircle size={11} aria-hidden="true" /> Not saved</span>;
  if (state === "conflict") return (
    <span className="grid-save grid-save-bad">Changed in another window. <button type="button" className="portal-link-btn" onClick={onReload}>Reload</button></span>
  );
  return null;
}

function ImportFromFile({ api, stage, fileName, onApplied }: { api: Api; stage: string; fileName: string; onApplied: (t: string) => void }) {
  const [preview, setPreview] = useState<{ cells: number; students: number; not_available: string[]; names: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/teacher/activities-grid/${stage}/import-upload`;
  const run = async (apply: boolean) => {
    setError(null);
    try {
      const res = await call<any>(api, "POST", url, { file_name: fileName, apply, expected_cells: apply ? preview?.cells : undefined });
      if (apply) { setPreview(null); onApplied(`Brought in ${res.cells} choice${res.cells === 1 ? "" : "s"} from ${fileName}. The original file was backed up.`); }
      else setPreview(res);
    } catch (e: any) {
      setError(e.message);
    }
  };
  return (
    <div className="grid-import">
      <span><FileUp size={14} aria-hidden="true" /> Bring in activities from the uploaded file <b>{fileName}</b> (older Excel layout).</span>
      <button type="button" className="btn btn-outline" onClick={() => run(false)}>Check the file</button>
      {preview && (
        <span aria-live="polite">
          {preview.cells === 0 ? "Nothing new in the file." : <>{preview.cells} choice(s) for {preview.students} student(s) differ from the grid.</>}
          {preview.not_available.length > 0 && <> Not available any more for: {preview.not_available.join(", ")}.</>}
          {preview.cells > 0 && <button type="button" className="btn btn-green" onClick={() => run(true)}>Bring them in</button>}
        </span>
      )}
      {error && <span className="grid-save-bad" role="alert">{error}</span>}
    </div>
  );
}
