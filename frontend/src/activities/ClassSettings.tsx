import { useEffect, useId, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { ApiError, call } from "../api";
import type { Api } from "../api";

// Class settings for one stage, set once (replaces the old workbook's first sheet). They fill these
// fields for every student; a student who differs gets a row on the Excel file's Exceptions sheet.

interface SettingsView {
  stage: string;
  values: { medium: string; rural_urban: string; working_days: (number | null)[]; max_marks: Record<string, number | null>; declaration: string };
  missing: string[];
  complete: boolean;
  version: number;
  updated_at: string | null;
  marks_subjects: { n: string; name: string }[];
  months: { key: string; name: string; max: number }[];
  choices: { medium: string[]; rural_urban: string[]; loaded: boolean };
  warnings?: Record<string, string>;
  from_school?: { working_days: boolean[]; max_marks: boolean };
}

type Form = { medium: string; rural_urban: string; working_days: string[]; max_marks: Record<string, string>; declaration: string };

const toForm = (v: SettingsView): Form => ({
  medium: v.values.medium || "", rural_urban: v.values.rural_urban || "",
  working_days: v.values.working_days.map((d) => (d === null || d === undefined ? "" : String(d))),
  max_marks: Object.fromEntries(v.marks_subjects.map((s) => [s.n, v.values.max_marks?.[s.n] == null ? "" : String(v.values.max_marks[s.n])])),
  declaration: v.values.declaration || "",
});

export function ClassSettings({ api, stage, onSaved }: { api: Api; stage: string; onSaved?: () => void }) {
  const [view, setView] = useState<SettingsView | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [baseline, setBaseline] = useState("");
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [warnings, setWarnings] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [same, setSame] = useState("");
  const id = useId();

  const load = async () => {
    try {
      const v = await call<SettingsView>(api, "GET", `/teacher/settings/${stage}`);
      setView(v);
      const f = toForm(v);
      setForm(f);
      setBaseline(JSON.stringify(f));
      setProblems({});
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    }
  };
  useEffect(() => { load(); }, [stage]);   // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = form !== null && JSON.stringify(form) !== baseline;
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Instant checks while typing; the server checks again on save.
  const local = useMemo(() => {
    const out: Record<string, string> = {};
    if (!form || !view) return out;
    view.months.forEach((m, i) => {
      const t = form.working_days[i].trim();
      if (!t) return;
      if (!/^\d+$/.test(t)) out[`working_days.${i}`] = `${m.name}: use a whole number.`;
      else if (Number(t) > m.max) out[`working_days.${i}`] = `${m.name}: between 0 and ${m.max}.`;
    });
    view.marks_subjects.forEach((s) => {
      const t = form.max_marks[s.n].trim();
      if (t && !(Number(t) > 0)) out[`max_marks.${s.n}`] = `${s.name}: must be more than 0.`;
    });
    return out;
  }, [form, view]);
  const allProblems = { ...problems, ...local };
  const total = form ? form.working_days.reduce((n, d) => n + (Number(d) || 0), 0) : 0;

  const set = (patch: Partial<Form>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const save = async () => {
    if (!form || !view || Object.keys(local).length) return;
    setSaving(true);
    setMessage(null);
    try {
      const body = {
        values: {
          medium: form.medium, rural_urban: form.rural_urban, declaration: form.declaration,
          working_days: form.working_days.map((d) => (d.trim() === "" ? null : Number(d))),
          max_marks: Object.fromEntries(Object.entries(form.max_marks).map(([n, m]) => [n, m.trim() === "" ? null : Number(m)])),
        },
        version: view.version,
      };
      const v = await call<SettingsView>(api, "PUT", `/teacher/settings/${stage}`, body);
      setView({ ...v, choices: view.choices });
      const f = toForm({ ...v, choices: view.choices });
      setForm(f);
      setBaseline(JSON.stringify(f));
      setProblems({});
      setWarnings(v.warnings || {});
      setMessage({ type: "success", text: v.complete ? "Settings saved. The Excel template can now be made." : "Settings saved. Some are still missing (see below)." });
      onSaved?.();
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 422 && (e.detail as any)?.problems) {
        setProblems((e.detail as any).problems);
        setWarnings((e.detail as any).warnings || {});
        setMessage({ type: "error", text: "Some values need fixing (shown in red)." });
      } else if (e instanceof ApiError && e.status === 409) {
        setMessage({ type: "error", text: e.message });
      } else {
        setMessage({ type: "error", text: e.message });
      }
    } finally {
      setSaving(false);
    }
  };

  if (!view || !form) {
    return <div className="ui-panel"><div className="lib-skeleton" aria-busy="true" aria-label="Loading class settings"><div className="lib-skeleton-row"><span /><span /><span /></div></div></div>;
  }

  return (
    <div className="ui-panel cs-panel">
      <div className="panel-header">
        <div className="panel-title"><CheckCircle2 size={20} color="#046A38" aria-hidden="true" /><span>Class settings – {stage}</span></div>
        <span className={`lib-badge ${view.complete ? "lib-badge-ok" : "lib-badge-warn"}`}>{view.complete ? "Complete" : "Not complete yet"}</span>
      </div>
      <p className="lib-muted">Set these once for the whole class. They fill the same fields for every student. If one student is different (for example joined late), add a row on the Excel file's <b>Exceptions</b> sheet.</p>

      <div aria-live="polite">
        {message && (
          <div className={`alert-box alert-${message.type} lib-inline-alert`} role={message.type === "error" ? "alert" : "status"}>
            {message.type === "error" ? <AlertCircle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}<div>{message.text}</div>
          </div>
        )}
      </div>
      {!view.complete && <p className="lib-note">Still to set: {view.missing.join("; ")}.</p>}

      <fieldset className="lib-fieldset">
        <legend className="form-label">School and language</legend>
        {!view.choices.loaded && <p className="lib-muted">Connect to PARAKH to load the lists of choices.</p>}
        <div className="lib-two">
          <div className="form-group">
            <label className="form-label" htmlFor={`${id}-med`}>Medium of instruction</label>
            <select id={`${id}-med`} className="form-select" value={form.medium} disabled={!view.choices.loaded && !form.medium}
                    onChange={(e) => set({ medium: e.target.value })}>
              <option value="">— Choose —</option>
              {(view.choices.medium.length ? view.choices.medium : form.medium ? [form.medium] : []).map((o) => <option key={o}>{o}</option>)}
            </select>
            {allProblems.medium && <div className="field-problem">{allProblems.medium}</div>}
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor={`${id}-ru`}>Rural / Urban</label>
            <select id={`${id}-ru`} className="form-select" value={form.rural_urban} disabled={!view.choices.loaded && !form.rural_urban}
                    onChange={(e) => set({ rural_urban: e.target.value })}>
              <option value="">— Choose —</option>
              {(view.choices.rural_urban.length ? view.choices.rural_urban : form.rural_urban ? [form.rural_urban] : []).map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="lib-fieldset">
        <legend className="form-label">Working days each month</legend>
        {view.from_school?.working_days.some(Boolean) && (
          <p className="lib-muted">The months marked "school" come from the School Register and are used on every save to PARAKH;
            you only need to fill a month the school left empty.</p>)}
        <div className="cs-tools">
          <button type="button" className="portal-link-btn" onClick={() => set({ working_days: form.working_days.map(() => form.working_days[0]) })}
                  disabled={!form.working_days[0]}>Copy April to every month</button>
          <span className="lib-muted">Total for the year: <b>{total}</b></span>
        </div>
        <div className="cs-months">
          {view.months.map((m, i) => {
            const key = `working_days.${i}`;
            return (
              <div key={m.key} className="cs-month">
                <label htmlFor={`${id}-m-${i}`}>{m.name}{view.from_school?.working_days[i] && <small className="cs-school"> school</small>}</label>
                <input id={`${id}-m-${i}`} className={`form-input ${allProblems[key] ? "cs-bad" : ""}`} inputMode="numeric" value={form.working_days[i]}
                       aria-invalid={!!allProblems[key]} aria-describedby={allProblems[key] || warnings[key] ? `${id}-wd-${i}` : undefined}
                       onChange={(e) => set({ working_days: form.working_days.map((d, j) => (j === i ? e.target.value : d)) })} />
                {(allProblems[key] || warnings[key]) && (
                  <small id={`${id}-wd-${i}`} className={allProblems[key] ? "field-problem" : "cs-warn"}>{allProblems[key] || warnings[key]}</small>
                )}
              </div>
            );
          })}
        </div>
      </fieldset>

      {view.marks_subjects.length > 0 && (
        <fieldset className="lib-fieldset">
          <legend className="form-label">Maximum summative marks per subject</legend>
          {view.from_school?.max_marks && (
            <p className="lib-muted">From the School Register (used on every save to PARAKH) - nothing to set here.</p>)}
          <div className="cs-tools">
            <label className="cs-inline">Same for every subject:
              <input className="form-input cs-small" inputMode="decimal" value={same} onChange={(e) => setSame(e.target.value)} />
            </label>
            <button type="button" className="portal-link-btn" disabled={!(Number(same) > 0)}
                    onClick={() => set({ max_marks: Object.fromEntries(view.marks_subjects.map((s) => [s.n, same])) })}>Apply to all</button>
          </div>
          <div className="cs-marks">
            {view.marks_subjects.map((s) => {
              const key = `max_marks.${s.n}`;
              return (
                <div key={s.n} className="cs-month">
                  <label htmlFor={`${id}-mm-${s.n}`}>{s.name}</label>
                  <input id={`${id}-mm-${s.n}`} className={`form-input ${allProblems[key] ? "cs-bad" : ""}`} inputMode="decimal" value={form.max_marks[s.n]}
                         aria-invalid={!!allProblems[key]} aria-describedby={allProblems[key] ? `${id}-mmp-${s.n}` : undefined}
                         onChange={(e) => set({ max_marks: { ...form.max_marks, [s.n]: e.target.value } })} />
                  {allProblems[key] && <small id={`${id}-mmp-${s.n}`} className="field-problem">{allProblems[key]}</small>}
                </div>
              );
            })}
          </div>
          <p className="lib-muted">Marks obtained are filled for each student in the Excel file and cannot be more than these.</p>
        </fieldset>
      )}

      <fieldset className="lib-fieldset">
        <legend className="form-label">Declaration (HPC Credit)</legend>
        <p className="lib-muted">The teacher's confirmation on the last page of the card.</p>
        <div className="lib-radios">
          {["Yes", "No"].map((v) => (
            <label key={v} className="lib-radio"><input type="radio" name={`${id}-decl`} checked={form.declaration === v}
                   onChange={() => set({ declaration: v })} /> {v}</label>
          ))}
        </div>
      </fieldset>

      <div className="cs-actions">
        {dirty && <span className="lib-unsaved" role="status">Unsaved changes</span>}
        <button type="button" className="btn btn-outline" onClick={load} disabled={saving}><RefreshCw size={14} aria-hidden="true" /> Reload</button>
        <button type="button" className="btn btn-green" onClick={save} disabled={!dirty || saving || Object.keys(local).length > 0}>
          <Save size={15} aria-hidden="true" /> {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </div>
  );
}
