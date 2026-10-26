import { useEffect, useId, useMemo, useState } from "react";
import { useBlocker } from "react-router-dom";
import { AlertCircle, CheckCircle2, History, RefreshCw, RotateCcw, Save } from "lucide-react";
import { ApiError, call } from "../api";
import type { Api } from "../api";
import { Modal } from "./Dialog";
import { useConfirm } from "./useConfirm";
import { CoverageBadge, SourceBadge } from "./Badges";
import { ABILITIES, LEVELS, SOURCE_LABEL, formatWhen } from "./types";
import type { ActivityDetail, Rubric, ShareLevel, Subject } from "./types";

// View, edit or create one activity. Edits are saved to this app only, never to PARAKH.

interface Form {
  title: string;
  display_name: string;
  activity_text: string;
  assessment_text: string;
  rubric: Rubric;
  goals: string;
  competencies: string;
  subjects: string[];
}

const emptyRubric = (): Rubric => ({
  awareness: { beginner: "", proficient: "", advanced: "" },
  sensitivity: { beginner: "", proficient: "", advanced: "" },
  creativity: { beginner: "", proficient: "", advanced: "" },
});

const toForm = (a: ActivityDetail): Form => ({
  title: a.title, display_name: a.source === "local" ? "" : a.title,
  activity_text: a.activity_text, assessment_text: a.assessment_text, rubric: a.rubric,
  goals: a.goals.join(", "), competencies: a.competencies.join(", "), subjects: a.subjects,
});

const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

const SHARE_OPTIONS: { value: ShareLevel; label: string; hint: string }[] = [
  { value: "private", label: "Only me", hint: "You and your school admin can see it." },
  { value: "school", label: "My school", hint: "Every teacher in your school can use it." },
  { value: "community", label: "Teachers in other schools too", hint: "Helps the shared bank grow. Checked by the app team before others see it." },
];

export function ActivityEditor({ api, stage, subjects, activityId, consentText, isAdmin, onClose, onSaved }: {
  api: Api;
  stage: string;
  isAdmin: boolean;
  subjects: Subject[];
  activityId: string | null;          // null = new activity
  consentText: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const creating = activityId === null;
  const [detail, setDetail] = useState<ActivityDetail | null>(null);
  const [form, setForm] = useState<Form | null>(creating ? {
    title: "", display_name: "", activity_text: "", assessment_text: "", rubric: emptyRubric(),
    goals: "", competencies: "", subjects: subjects.map((s) => s.code),
  } : null);
  const [baseline, setBaseline] = useState<string>(() => (creating ? JSON.stringify(form) : ""));   // what "no changes" means
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [share, setShare] = useState<ShareLevel>(isAdmin ? "school" : "private");
  const [consent, setConsent] = useState(false);
  const [confirmUi, confirm] = useConfirm();
  const ids = { title: useId(), name: useId(), desc: useId(), assess: useId(), goals: useId(), cpt: useId(), consent: useId() };

  const load = async () => {
    if (!activityId) return;
    setLoadError(null);
    try {
      const d = await call<ActivityDetail>(api, "GET", `/activity-library/${activityId}`);
      setDetail(d);
      const f = toForm(d);
      setForm(f);
      setBaseline(JSON.stringify(f));
      setShare(d.share_state === "community_ok" ? "community" : (d.share_state as ShareLevel) || "private");
      setConsent(false);
      setConflict(false);
    } catch (e: any) {
      setLoadError(e.message);
    }
  };
  useEffect(() => { load(); }, [activityId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = form !== null && JSON.stringify(form) !== baseline;
  const editable = creating || !!detail?.can_edit;
  const isLocal = creating || detail?.source === "local";
  const canRename = !!detail?.can_manage && !isLocal;
  const currentShare = detail?.share_state === "community_ok" ? "community" : detail?.share_state;
  const shareOrder: ShareLevel[] = ["private", "school", "community"];
  const widening = shareOrder.indexOf(share) > shareOrder.indexOf((currentShare as ShareLevel) || "private");
  const canShare = isLocal && editable;
  // Same rule as the server: the maker agrees before their activity is shared more widely;
  // sharing with other schools always needs agreement.
  const teacherMade = creating ? !isAdmin : !!detail?.is_mine;
  const needsConsent = (creating || widening) && share !== "private" && (teacherMade || share === "community");
  const shareOptions = isAdmin && (creating || !detail?.is_mine) ? SHARE_OPTIONS.filter((o) => o.value !== "private") : SHARE_OPTIONS;

  // Unsaved changes: warn before closing the tab or following a link.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const blocker = useBlocker(dirty && !saving);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    confirm({ title: "Leave without saving?", message: "Your changes to this activity have not been saved.", confirmLabel: "Leave", danger: true })
      .then((ok) => (ok ? blocker.proceed() : blocker.reset()));
  }, [blocker.state]);   // eslint-disable-line react-hooks/exhaustive-deps

  const close = async () => {
    if (dirty && !(await confirm({ title: "Discard changes?", message: "Your changes to this activity have not been saved.",
                                   confirmLabel: "Discard changes", danger: true }))) return;
    onClose();
  };

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => (f ? { ...f, [key]: value } : f));
  const setRubric = (a: keyof Rubric, l: keyof Rubric["awareness"], v: string) =>
    setForm((f) => (f ? { ...f, rubric: { ...f.rubric, [a]: { ...f.rubric[a], [l]: v } } } : f));

  const changes = useMemo(() => {
    if (!form) return {};
    const was: Form = baseline ? JSON.parse(baseline) : form;
    const out: Record<string, unknown> = {};
    if (editable) {
      if (form.activity_text !== was.activity_text) out.activity_text = form.activity_text;
      if (form.assessment_text !== was.assessment_text) out.assessment_text = form.assessment_text;
      if (JSON.stringify(form.subjects) !== JSON.stringify(was.subjects)) out.subjects = form.subjects;
      const rubric: Record<string, Record<string, string>> = {};
      for (const a of ABILITIES) for (const l of LEVELS) {
        if (form.rubric[a.key][l.key] !== was.rubric[a.key][l.key]) (rubric[a.key] ||= {})[l.key] = form.rubric[a.key][l.key];
      }
      if (Object.keys(rubric).length) out.rubric = rubric;
      if (isLocal) {
        if (form.title !== was.title) out.title = form.title;
        if (form.goals !== was.goals) out.goals = splitList(form.goals);
        if (form.competencies !== was.competencies) out.competencies = splitList(form.competencies);
      }
    }
    if (canRename && form.display_name !== was.display_name) out.display_name = form.display_name;
    return out;
  }, [form, baseline, editable, isLocal, canRename]);

  const problems: string[] = [];
  if (form && isLocal && !form.title.trim()) problems.push("Give the activity a name.");
  if (form && form.subjects.length === 0) problems.push("Choose at least one subject.");
  if (needsConsent && !consent && creating) problems.push("Tick the sharing agreement, or choose who can use it again.");

  const save = async () => {
    if (!form || problems.length) return;
    setSaving(true);
    setSaveError(null);
    try {
      if (creating) {
        const body = { stage, title: form.title, activity_text: form.activity_text, assessment_text: form.assessment_text,
                       rubric: form.rubric, goals: splitList(form.goals), competencies: splitList(form.competencies),
                       subjects: form.subjects, ...(share !== "private" ? { share, consent } : {}) };
        const made = await call<ActivityDetail>(api, "POST", "/activity-library", body);
        setBaseline(JSON.stringify(form));
        onSaved(`"${made.label}" was added to the library.`);
        onClose();
        return;
      }
      const d = await call<ActivityDetail>(api, "PATCH", `/activity-library/${activityId}`, { ...changes, version: detail?.version });
      setDetail(d);
      const f = toForm(d);
      setForm(f);
      setBaseline(JSON.stringify(f));
      onSaved(`Changes to "${d.label}" were saved.`);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      else setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const saveShare = async () => {
    if (!detail) return;
    try {
      const d = await call<ActivityDetail>(api, "POST", `/activity-library/${detail.id}/share`, { level: share, consent });
      setDetail(d);
      setConsent(false);
      onSaved(share === "private" ? "Sharing stopped." : `Sharing changed to "${SHARE_OPTIONS.find((o) => o.value === share)?.label}".`);
    } catch (e: any) {
      setSaveError(e.message);
    }
  };

  const resetToOriginal = async () => {
    if (!detail) return;
    if (!(await confirm({ title: "Go back to the PARAKH original?",
                          message: "Your school's changes to the texts and subjects of this activity will be removed. The name shown in Excel is kept.",
                          confirmLabel: "Go back to original", danger: true }))) return;
    try {
      const d = await call<ActivityDetail>(api, "POST", `/activity-library/${detail.id}/reset`);
      setDetail(d);
      const f = toForm(d);
      setForm(f);
      setBaseline(JSON.stringify(f));
      onSaved(`"${d.label}" is back to the PARAKH original.`);
    } catch (e: any) {
      setSaveError(e.message);
    }
  };

  const title = creating ? `New ${stage} activity` : detail ? detail.label : "Activity";
  const footer = form && (
    <>
      {dirty && <span className="lib-unsaved" role="status">Unsaved changes</span>}
      <button type="button" className="btn btn-outline" onClick={close}>{editable || canRename ? "Cancel" : "Close"}</button>
      {(editable || canRename) && (
        <button type="button" className="btn btn-green" onClick={save} disabled={(!dirty && !creating) || saving || problems.length > 0}>
          {saving ? <RefreshCw size={15} className="spin" aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}
          {creating ? "Add activity" : "Save changes"}
        </button>
      )}
    </>
  );

  return (
    <Modal wide title={title} onClose={close} footer={footer}
           subtitle={detail && <span className="lib-badges"><SourceBadge source={detail.source} /><CoverageBadge activity={detail} />
             {detail.edited && <span className="lib-badge lib-badge-edited">Changed by your school</span>}</span>}>
      {loadError ? (
        <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" />
          <div>{loadError} <button type="button" className="portal-link-btn" onClick={load}>Try again</button></div></div>
      ) : !form ? (
        <div className="lib-skeleton-block" aria-busy="true" aria-label="Loading activity"><span /><span /><span /></div>
      ) : (
        <div className="lib-editor">
          {conflict && (
            <div className="alert-box alert-warning" role="alert"><AlertCircle size={18} aria-hidden="true" />
              <div>Someone else changed this activity while you were editing. <button type="button" className="portal-link-btn" onClick={load}>Load their version</button> (your changes here will be lost).</div></div>
          )}
          {saveError && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{saveError}</div></div>}
          {detail && !detail.usable_in_excel && <p className="lib-note"><AlertCircle size={14} aria-hidden="true" /> Not offered in the Excel sheet: {detail.not_usable_reason}</p>}
          {detail && !isLocal && (
            <p className="lib-muted">From the {SOURCE_LABEL[detail.source]} (PARAKH number {detail.portal_id}). Changes you make here are kept in this app only; PARAKH is not changed.</p>
          )}

          {isLocal ? (
            <div className="form-group">
              <label className="form-label" htmlFor={ids.title}>Activity name <span className="req" aria-hidden="true">*</span></label>
              <input id={ids.title} className="form-input" value={form.title} maxLength={200} disabled={!editable} required
                     aria-required="true" data-autofocus onChange={(e) => set("title", e.target.value)} />
            </div>
          ) : (
            <div className="lib-two">
              <div className="form-group">
                <span className="form-label">Code on PARAKH</span>
                <div className="mono-chip lib-code">{detail?.code}</div>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor={ids.name}>Name shown in Excel (optional)</label>
                <input id={ids.name} className="form-input" value={form.display_name} maxLength={120} disabled={!canRename}
                       placeholder="e.g. Asking politely" onChange={(e) => set("display_name", e.target.value)} />
              </div>
            </div>
          )}

          <fieldset className="lib-fieldset" disabled={!editable}>
            <legend className="form-label">Subjects this activity can be used for</legend>
            <div className="lib-subject-tools">
              <button type="button" className="portal-link-btn" onClick={() => set("subjects", subjects.map((s) => s.code))}>All subjects</button>
              <button type="button" className="portal-link-btn" onClick={() => set("subjects", [])}>None</button>
              {detail && !isLocal && detail.portal_subject_names.length > 0 && (
                <span className="lib-muted">On PARAKH it is listed under: {detail.portal_subject_names.join(", ")}</span>
              )}
            </div>
            <div className="lib-checks">
              {subjects.map((s) => (
                <label key={s.code} className="lib-check">
                  <input type="checkbox" checked={form.subjects.includes(s.code)}
                         onChange={(e) => set("subjects", e.target.checked
                           ? subjects.map((x) => x.code).filter((c) => c === s.code || form.subjects.includes(c))
                           : form.subjects.filter((c) => c !== s.code))} />
                  {s.name}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="form-group">
            <label className="form-label" htmlFor={ids.desc}>How the activity is done</label>
            <textarea id={ids.desc} className="form-input lib-textarea" rows={5} value={form.activity_text} disabled={!editable}
                      onChange={(e) => set("activity_text", e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor={ids.assess}>How it is assessed</label>
            <textarea id={ids.assess} className="form-input lib-textarea" rows={3} value={form.assessment_text} disabled={!editable}
                      onChange={(e) => set("assessment_text", e.target.value)} />
          </div>

          {ABILITIES.map((a) => (
            <fieldset key={a.key} className="lib-fieldset" disabled={!editable}>
              <legend className="form-label">{a.label}: what each level looks like</legend>
              <div className="lib-levels">
                {LEVELS.map((l) => (
                  <label key={l.key} className="lib-level">
                    <span>{l.label}</span>
                    <textarea className="form-input" rows={3} value={form.rubric[a.key][l.key]}
                              onChange={(e) => setRubric(a.key, l.key, e.target.value)} />
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          <div className="lib-two">
            <div className="form-group">
              <label className="form-label" htmlFor={ids.goals}>Curricular goal code(s)</label>
              <input id={ids.goals} className="form-input" value={form.goals} disabled={!editable || !isLocal}
                     placeholder="e.g. L1CG1" onChange={(e) => set("goals", e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor={ids.cpt}>Competency code(s)</label>
              <input id={ids.cpt} className="form-input" value={form.competencies} disabled={!editable || !isLocal}
                     placeholder="e.g. L1C1.1" onChange={(e) => set("competencies", e.target.value)} />
            </div>
          </div>

          {isLocal && detail && !detail.portal_ready.ok && (
            <p className="lib-note">To be added to PARAKH later, this activity still needs: {detail.portal_ready.missing.join(", ")}.</p>
          )}

          {detail && !isLocal && (detail.diff?.length ?? 0) > 0 && (
            <section className="lib-diff" aria-labelledby="lib-diff-title">
              <div className="lib-diff-head">
                <h3 id="lib-diff-title" className="lib-section-title">Your school's changes compared with PARAKH</h3>
                {detail.can_manage && (
                  <button type="button" className="btn btn-outline" onClick={resetToOriginal}>
                    <RotateCcw size={14} aria-hidden="true" /> Go back to original
                  </button>
                )}
              </div>
              <table className="data-table lib-diff-table">
                <thead><tr><th scope="col">What</th><th scope="col">On PARAKH</th><th scope="col">Your school</th></tr></thead>
                <tbody>
                  {detail.diff!.map((d) => (
                    <tr key={d.field}>
                      <th scope="row">{d.label}</th>
                      <td><del>{Array.isArray(d.original) ? d.original.join(", ") : String(d.original || "(empty)")}</del></td>
                      <td><ins>{Array.isArray(d.current) ? d.current.join(", ") : String(d.current || "(empty)")}</ins></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {canShare && (
            <fieldset className="lib-fieldset">
              <legend className="form-label">Who can use this activity</legend>
              <div className="lib-radios">
                {shareOptions.map((o) => (
                  <label key={o.value} className="lib-radio">
                    <input type="radio" name="share" value={o.value} checked={share === o.value} onChange={() => { setShare(o.value); setConsent(false); }} />
                    <span><b>{o.label}</b><span className="lib-muted"> — {o.hint}</span></span>
                  </label>
                ))}
              </div>
              {detail?.share_state === "community" && <p className="lib-muted">Shared with other schools: waiting for the app team to check it.</p>}
              {needsConsent && (
                <label className="lib-consent" htmlFor={ids.consent}>
                  <input id={ids.consent} type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                  <span>{consentText}</span>
                </label>
              )}
              {!creating && share !== currentShare && (
                <button type="button" className="btn btn-outline" onClick={saveShare} disabled={needsConsent && !consent}>
                  Save who can use it
                </button>
              )}
            </fieldset>
          )}

          {problems.length > 0 && (dirty || creating) && (
            <ul className="lib-problems" aria-live="polite">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
          )}

          {detail && detail.history.length > 0 && (
            <details className="lib-history">
              <summary><History size={14} aria-hidden="true" /> Change history</summary>
              <ul>{detail.history.map((h, i) => <li key={i}>{formatWhen(h.at)} · {h.who} · {HISTORY_LABEL[h.action] || h.action}</li>)}</ul>
            </details>
          )}
          {detail && !isLocal && detail.last_synced_at && (
            <p className="lib-muted"><CheckCircle2 size={13} aria-hidden="true" /> Last read from PARAKH: {formatWhen(detail.last_synced_at)}</p>
          )}
        </div>
      )}
      {confirmUi}
    </Modal>
  );
}

const HISTORY_LABEL: Record<string, string> = {
  create: "added", edit: "changed", status: "turned on/off", reset: "went back to the PARAKH original",
  duplicate: "copied", share: "changed who can use it", set_default: "made default", clear_default: "stopped being default",
};
