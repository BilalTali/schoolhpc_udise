import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";
import { useCardCheck } from "./useCardCheck";
import { ConnectPrompt, ReadingFromParakh } from "./ConnectPrompt";
import { Modal } from "./Dialog";
import { needsParakh } from "./parakhConnect";

// Part C levels for the whole class on one screen (Bulk Entry). Saved into each student's draft; they are
// pre-filled in the Excel download and reach PARAKH with the card or the uploaded file.

interface LevelsData {
  options: string[];
  subjects: { code: string; name: string; fields: { key: string; ability: string }[] }[];
  rows: { student_id: string; student_name: string; grade: string; section: string;
          values: Record<string, string>; portal: Record<string, string>; in_draft: string[] }[];
  read_at?: string | null;            // when the stored copy was read from PARAKH (oldest student)
}

export function LevelsGrid({ api, stage }: { api: Api; stage: string }) {
  const [data, setData] = useState<LevelsData | null>(null);
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [fill, setFill] = useState("");
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);              // PARAKH not connected
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());            // students to set levels for together
  const [plan, setPlan] = useState<Record<string, string>>({});            // field key -> level to apply ("" = leave)
  const [planOpen, setPlanOpen] = useState(false);                         // the "set their levels" pop-up

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setMessage(null);
    try {
      setData(await call<LevelsData>(api, "GET", `/teacher/hpc-cards/${encodeURIComponent(stage)}/levels${refresh ? "?refresh=true" : ""}`));
      setEdits({});
      setProblems({});
    } catch (e: any) {
      if (needsParakh(e)) {
        setOffline(true);           // nothing shown yet: the connect prompt; already shown: say why it did not refresh
        setMessage({ type: "error", text: "The PARAKH connection has ended. Press 'Connect' at the top right, then 'Read again from PARAKH'." });
      } else setMessage({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  }, [api, stage]);
  useEffect(() => { load(); }, [load]);

  const [changedOnParakh, setChangedOnParakh] = useState<string[]>([]);   // shown when there are unsaved edits
  const editsRef = useRef(edits);
  useEffect(() => { editsRef.current = edits; });
  const checking = useCardCheck(api, stage, !!data, (ids) => {
    if (Object.keys(editsRef.current).length) setChangedOnParakh(ids);
    else load().then(() => setMessage({ type: "success", text: `Updated from PARAKH: ${ids.length} student${ids.length === 1 ? "'s card was" : "s' cards were"} changed there.` }));
  });

  const keys = useMemo(() => (data?.subjects || []).flatMap((s) => s.fields.map((f) => f.key)), [data]);
  const valueOf = (sid: string, key: string, saved: string) => edits[sid]?.[key] ?? saved;
  const changed = useMemo(() => {
    const out: Record<string, Record<string, string>> = {};
    for (const r of data?.rows || []) {
      for (const [k, v] of Object.entries(edits[r.student_id] || {})) {
        if (v !== (r.values[k] || "")) (out[r.student_id] ||= {})[k] = v;
      }
    }
    return out;
  }, [edits, data]);
  const count = Object.values(changed).reduce((n, m) => n + Object.keys(m).length, 0);
  const empty = (data?.rows || []).reduce((n, r) => n + keys.filter((k) => !valueOf(r.student_id, k, r.values[k] || "")).length, 0);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (count) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [count]);

  // stable, so a row only draws again when its own levels change (Middle: 35 students x 33 levels)
  const set = useCallback((sid: string, key: string, v: string) =>
    setEdits((e) => ({ ...e, [sid]: { ...(e[sid] || {}), [key]: v } })), []);
  const fillEmpty = () => {
    if (!fill || !data) return;
    const next = { ...edits };
    for (const r of data.rows) for (const k of keys) {
      if (!valueOf(r.student_id, k, r.values[k] || "")) next[r.student_id] = { ...(next[r.student_id] || {}), [k]: fill };
    }
    setEdits(next);
  };
  // mixed levels: for each subject and ability, Beginner / Proficient / Advanced handed out at random, each about
  // equally often (a shuffled round, again and again); empty levels only unless every level is redone. Saved with
  // "Save levels", like any other change here.
  const mixLevels = (everyLevel: boolean) => {
    if (!data || !data.options.length) return;
    const next = { ...edits };
    for (const k of keys) {
      let round: string[] = [];
      for (const r of data.rows) {
        if (!everyLevel && valueOf(r.student_id, k, r.values[k] || "")) continue;
        if (!round.length) {
          round = [...data.options];
          for (let i = round.length - 1; i > 0; i--) {             // Fisher-Yates
            const j = Math.floor(Math.random() * (i + 1));
            [round[i], round[j]] = [round[j], round[i]];
          }
        }
        next[r.student_id] = { ...(next[r.student_id] || {}), [k]: round.pop()! };
      }
    }
    setEdits(next);
    setMessage({ type: "success", text: `Mixed ${everyLevel ? "every" : "the empty"} level${everyLevel ? "" : "s"}. Check them in the table, then press Save levels.` });
  };

  const abilities = useMemo(() => {
    const out: string[] = [];
    for (const sub of data?.subjects || []) for (const f of sub.fields) if (!out.includes(f.ability)) out.push(f.ability);
    return out;
  }, [data]);
  const toggle = useCallback((sid: string) =>
    setTicked((t) => { const n = new Set(t); if (n.has(sid)) n.delete(sid); else n.add(sid); return n; }), []);
  const everySubject = (ability: string, level: string) => setPlan((p) => {
    const n = { ...p };
    for (const sub of data?.subjects || []) for (const f of sub.fields) if (f.ability === ability) n[f.key] = level;
    return n;
  });
  const planned = Object.values(plan).filter(Boolean).length;
  const applyPlan = () => {
    if (!data || !planned) return;
    const next = { ...edits };
    for (const sid of ticked) {
      for (const [key, level] of Object.entries(plan)) if (level) next[sid] = { ...(next[sid] || {}), [key]: level };
    }
    setEdits(next);
    setMessage({ type: "success", text: `Set ${planned} level${planned === 1 ? "" : "s"} for ${ticked.size} student${ticked.size === 1 ? "" : "s"}. Check them in the table, then press Save levels.` });
    setTicked(new Set());
    setPlan({});
    setPlanOpen(false);
  };

  const save = async () => {
    if (!count) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await call<{ saved: string[]; problems: Record<string, string> }>(
        api, "PUT", `/teacher/hpc-cards/${encodeURIComponent(stage)}/levels`, { values: changed });
      setProblems(res.problems);
      setData((d) => d && { ...d, rows: d.rows.map((r) => (res.saved.includes(r.student_id)
        ? { ...r, values: { ...r.values, ...changed[r.student_id] }, in_draft: [...new Set([...r.in_draft, ...Object.keys(changed[r.student_id])])] }
        : r)) });
      setEdits((e) => Object.fromEntries(Object.entries(e).filter(([sid]) => !res.saved.includes(sid))));
      const bad = Object.keys(res.problems).length;
      setMessage({ type: bad ? "warning" : "success",
                   text: `Saved for ${res.saved.length} student${res.saved.length === 1 ? "" : "s"}.${bad ? ` ${bad} could not be saved (shown in red).` : ""} They are pre-filled in your Excel download.` });
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  if (offline && !data) {
    return <div className="ui-panel"><ConnectPrompt what="the Part C levels" /></div>;
  }

  return (
    <div className="ui-panel">
      <div className="panel-header">
        <div className="panel-title"><CheckCircle2 size={20} color="#046A38" aria-hidden="true" /><span>Part C levels – whole class</span></div>
        <button type="button" className="btn btn-outline" onClick={() => load(true)} disabled={loading || saving || count > 0}
                title={count > 0 ? "Save or undo your changes first" : undefined}>
          <RefreshCw size={14} aria-hidden="true" className={loading ? "spin" : ""} /> Read again from PARAKH
        </button>
      </div>
      <p className="lib-muted">Most students are at the same level in most subjects. Fill the usual level for everyone, then tick the
        students who are different (for example all the Beginners), press "Set their levels…", and save.
        {data?.read_at && <> Loaded from the app's copy, read from PARAKH on {new Date(data.read_at).toLocaleString()}.</>}</p>

      <div aria-live="polite">
        {checking && <p className="lib-muted">Checking PARAKH for changes… ({checking.done} of {checking.total})</p>}
        {changedOnParakh.length > 0 && data && (
          <div className="alert-box alert-warning lib-inline-alert">
            <AlertCircle size={18} aria-hidden="true" />
            <div>Changed on PARAKH since your copy: {changedOnParakh.map((id) => data.rows.find((r) => r.student_id === id)?.student_name || id).join(", ")}.{" "}
              <button type="button" className="portal-link-btn" onClick={() => { setChangedOnParakh([]); load(); }}>
                Show the new values</button> (your unsaved changes here will be lost; save them first to keep them).</div>
          </div>
        )}
        {message && (
          <div className={`alert-box alert-${message.type} lib-inline-alert`} role={message.type === "error" ? "alert" : "status"}>
            {message.type === "success" ? <CheckCircle2 size={18} aria-hidden="true" /> : <AlertCircle size={18} aria-hidden="true" />}<div>{message.text}</div>
          </div>
        )}
      </div>

      {!data ? (
        loading && <ReadingFromParakh what="every student's Part C levels" />
      ) : (
        <>
          <div className="tp-row">
            <label className="cs-inline">Fill every empty level with
              <select className="form-select cs-small" value={fill} onChange={(e) => setFill(e.target.value)}>
                <option value="">—</option>
                {data.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-outline" onClick={fillEmpty} disabled={!fill || !empty}>Fill {empty} empty</button>
            <button type="button" className="btn btn-outline" onClick={() => mixLevels(false)} disabled={!empty}
                    title="Beginner, Proficient and Advanced at random, each about equally often">Mix {empty} empty</button>
            <button type="button" className="btn btn-outline" onClick={() => mixLevels(true)}
                    title="Redoes every level with Beginner, Proficient and Advanced at random">Mix all levels</button>
            <span className="lib-muted">{count ? `${count} unsaved change${count === 1 ? "" : "s"}` : "No unsaved changes"}</span>
            {ticked.size > 0 && (
              <span className="lv-ticked" role="status">
                <b>{ticked.size} ticked</b>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => setPlanOpen(true)}>Set their levels…</button>
                <button type="button" className="portal-link-btn" onClick={() => setTicked(new Set())}>Clear</button>
              </span>
            )}
            <button type="button" className="btn btn-outline" onClick={() => setEdits({})} disabled={!count || saving}>Undo changes</button>
            <button type="button" className="btn btn-green" onClick={save} disabled={!count || saving}>
              {saving ? <RefreshCw size={15} className="spin" aria-hidden="true" /> : <Save size={15} aria-hidden="true" />} Save levels
            </button>
          </div>

          {planOpen && ticked.size > 0 && (
            <Modal wide title={`Set levels for ${ticked.size} ticked student${ticked.size === 1 ? "" : "s"}`}
                   subtitle={<span className="lib-muted">Choose only what should change; "—" leaves a level as it is.</span>}
                   onClose={() => setPlanOpen(false)}
                   footer={<>
                     <button type="button" className="btn btn-outline" onClick={() => setPlanOpen(false)}>Back to ticking</button>
                     <button type="button" className="btn btn-primary" onClick={applyPlan} disabled={!planned}>
                       Apply to {ticked.size} ticked student{ticked.size === 1 ? "" : "s"}
                     </button>
                   </>}>
              <p className="lv-who">{data.rows.filter((r) => ticked.has(r.student_id)).map((r) => r.student_name).join(", ")}</p>
              <div className="lv-plan-scroll">
                <table className="lv-plan-table">
                  <thead><tr><th scope="col">Subject</th>{abilities.map((a) => <th key={a} scope="col">{a}</th>)}</tr></thead>
                  <tbody>
                    <tr className="lv-every">
                      <th scope="row">Every subject</th>
                      {abilities.map((a) => (
                        <td key={a}>
                          <select className="form-select" aria-label={`Every subject, ${a}`} defaultValue=""
                                  onChange={(e) => everySubject(a, e.target.value)}>
                            <option value="">—</option>
                            {data.options.map((o) => <option key={o}>{o}</option>)}
                          </select>
                        </td>
                      ))}
                    </tr>
                    {data.subjects.map((sub) => (
                      <tr key={sub.code}>
                        <th scope="row">{sub.name}</th>
                        {abilities.map((a) => {
                          const f = sub.fields.find((x) => x.ability === a);
                          return (
                            <td key={a}>
                              {f && (
                                <select className="form-select" aria-label={`${sub.name}, ${a}, for the ticked students`} value={plan[f.key] || ""}
                                        onChange={(e) => setPlan((p) => ({ ...p, [f.key]: e.target.value }))}>
                                  <option value="">—</option>
                                  {data.options.map((o) => <option key={o}>{o}</option>)}
                                </select>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Modal>
          )}

          <div className="grid-scroll" role="region" aria-label="Part C levels" tabIndex={0}>
            <table className="grid-table">
              <caption className="sr-only">Part C levels for each student, subject and ability.</caption>
              <thead>
                <tr>
                  <th scope="col" rowSpan={2} className="grid-sticky grid-student-head">
                    <input type="checkbox" aria-label="Tick every student"
                           checked={data.rows.length > 0 && ticked.size === data.rows.length}
                           onChange={() => setTicked(ticked.size === data.rows.length ? new Set() : new Set(data.rows.map((r) => r.student_id)))} />
                    <span>Student</span>
                  </th>
                  {data.subjects.map((s) => <th key={s.code} scope="colgroup" colSpan={s.fields.length} className="grid-subject-head">{s.name}</th>)}
                </tr>
                <tr>
                  {data.subjects.flatMap((s) => s.fields.map((f) => <th key={f.key} scope="col" className="grid-sub-head" title={f.ability}>{f.ability.slice(0, 3)}</th>))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <LevelRow key={r.student_id} row={r} subjects={data.subjects} options={data.options}
                            rowEdits={edits[r.student_id]} ticked={ticked.has(r.student_id)} problem={problems[r.student_id]}
                            onSet={set} onToggle={toggle} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="lib-muted">B = Beginner, P = Proficient, A = Advanced.</p>
        </>
      )}
    </div>
  );
}


// One student's row. Drawn again only when its own levels, tick or problem change - not when another student's
// level is changed (props are the same objects then).
const LevelRow = memo(function LevelRow({ row: r, subjects, options, rowEdits, ticked, problem, onSet, onToggle }: {
  row: LevelsData["rows"][number];
  subjects: LevelsData["subjects"];
  options: string[];
  rowEdits: Record<string, string> | undefined;
  ticked: boolean;
  problem: string | undefined;
  onSet: (sid: string, key: string, v: string) => void;
  onToggle: (sid: string) => void;
}) {
  return (
    <tr className={problem ? "grid-row-todo" : ""}>
      <th scope="row" className="grid-sticky grid-student">
        <input type="checkbox" checked={ticked} onChange={() => onToggle(r.student_id)} aria-label={`Tick ${r.student_name}`} />
        <span className="grid-name">
          <b>{r.student_name}</b>
          <small>{[r.grade, r.section && `Sec ${r.section}`].filter(Boolean).join(" · ")}</small>
          {problem && <small className="field-problem">{problem}</small>}
        </span>
      </th>
      {subjects.flatMap((s) => s.fields.map((f) => {
        const saved = r.values[f.key] || "";
        const v = rowEdits?.[f.key] ?? saved;
        return (
          <td key={f.key} className={v !== saved ? "row-edited" : ""}>
            <select className="form-select grid-level-select" value={v}
                    aria-label={`${r.student_name}, ${s.name}, ${f.ability}`}
                    onChange={(e) => onSet(r.student_id, f.key, e.target.value)}>
              <option value="">—</option>
              {options.map((o) => <option key={o} value={o}>{o[0]}</option>)}
            </select>
          </td>
        );
      }))}
    </tr>
  );
});
