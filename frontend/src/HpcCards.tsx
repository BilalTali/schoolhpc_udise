import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import {
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Save,
  Sparkles,
  Eye,
  Trash2,
  X,
  Printer,
  Clock,
  Layers,
} from "lucide-react";
import { ApiError, call } from "./api";
import type { Api } from "./api";
import { useCardCheck } from "./activities/useCardCheck";
import { ConnectPrompt } from "./activities/ConnectPrompt";
import { needsParakh } from "./activities/parakhConnect";

// Editor for one student's HPC card and bulk entry of one field across the class.
// Talks to backend/routers/hpc_cards.py. Edits are autosaved as a server-side draft;
// nothing reaches the PARAKH portal until the teacher presses Submit.

// ─── Types ─────────────────────────────────────────────────────────────────

type FieldValue = string | number | string[];

interface FieldMeta {
  key: string;
  label: string;
  kind: "text" | "int" | "choice" | "multi" | "onehot" | "flags" | "inlist";
  options: string[];
  max_len: number | null;
  required: boolean;
  multiple: boolean;
  suggestions?: string[];          // ready phrases for a text answer, offered next to the box
  mixable?: boolean;               // false: a fact about the student (mother tongue ...), never handed out at random
  mix_pool?: string[];             // a several-option question Mix may fill: the options it may hand out ...
  mix_pick?: number;               // ... and how many each student gets
  from_records?: string;           // "levels": a Part C note, written from the subject's own three levels
}

interface CardField extends FieldMeta {
  value: FieldValue;
  portal_value: FieldValue;
  changed: boolean;
  from_levels?: string;            // a Part C note: what the subject's levels give ("" without all three)
}

interface CardPart {
  code: string;
  title: string;
  fields: CardField[];
  problems: string[];
  warnings?: string[];             // reads wrong but PARAKH accepts it (never blocks a save)
  complete: boolean;
}

interface CardData {
  student: {
    student_id: string;
    student_name: string;
    stage: string;
    grade: string;
    section: string;
    apaar_id?: string;
    current_part?: string;
    completed: boolean;
  };
  session: { code: string; label: string };
  parts: CardPart[];
  ready: boolean;
  draft: { version: number; saved_at: string } | null;
}

interface PreviewData {
  student: CardData["student"];
  session: CardData["session"];
  sections: { code: string; title: string; items: { label: string; value: string }[]; complete: boolean }[];
  ready: boolean;
  includes_draft: boolean;
}

interface BulkRow {
  student_id: string;
  student_name: string;
  grade: string;
  section: string;
  status: string;
  value: FieldValue;
  portal_value: FieldValue;
  in_draft: boolean;
  from_levels?: string;            // a Part C note: what this student's levels give ("" without all three)
}

type SaveState = "idle" | "pending" | "saving" | "saved" | "conflict" | "error";

// ─── API ───────────────────────────────────────────────────────────────────

export type CardsApi = Api;

const cardPath = (stage: string, studentId: string) =>
  `/teacher/hpc-cards/${encodeURIComponent(stage)}/${encodeURIComponent(studentId)}`;

function isBlank(v: FieldValue | undefined) {
  return v === undefined || v === null || (Array.isArray(v) ? v.length === 0 : String(v).trim() === "");
}

function sameValue(a: FieldValue, b: FieldValue) {
  if (Array.isArray(a) || Array.isArray(b)) {
    const x = Array.isArray(a) ? a : [], y = Array.isArray(b) ? b : [];
    return x.length === y.length && x.every((v) => y.includes(v));
  }
  return String(a ?? "") === String(b ?? "");
}

function timeOf(iso: string) {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ─── One input for any field kind ──────────────────────────────────────────

function FieldInput({ field, value, onChange, disabled, compact }: {
  field: FieldMeta;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  if (field.multiple) {
    const chosen = Array.isArray(value) ? value : [];
    return (
      <div className="choice-chips">
        {field.options.map((opt) => {
          const on = chosen.includes(opt);
          return (
            <button
              key={opt}
              type="button"
              className={`choice-chip ${on ? "on" : ""}`}
              disabled={disabled}
              aria-pressed={on}
              onClick={() => onChange(on ? chosen.filter((c) => c !== opt) : [...chosen, opt])}
            >
              {on && <CheckCircle2 size={12} />} {opt}
            </button>
          );
        })}
      </div>
    );
  }
  if (field.options.length > 0) {
    return (
      <select className="form-select card-input" value={String(value ?? "")} disabled={disabled}
              onChange={(e) => onChange(e.target.value)}>
        <option value="">— Select —</option>
        {field.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    );
  }
  if (field.kind === "int") {
    return (
      <input type="number" step={1} className="form-input card-input" value={String(value ?? "")} disabled={disabled}
             onChange={(e) => onChange(e.target.value)} />
    );
  }
  const text = String(value ?? "");
  const long = !compact && (field.max_len === null || field.max_len > 80);
  return (
    <div className="card-text-wrap">
      {!!field.suggestions?.length && !disabled && (
        <select className="form-select card-suggest" value="" aria-label={`${field.label}: use a suggestion`}
                onChange={(e) => { if (e.target.value) onChange(e.target.value); }}>
          <option value="">Suggestions…</option>
          {field.suggestions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      )}
      {long ? (
        <textarea className="form-input card-input" rows={3} value={text} disabled={disabled}
                  onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input type="text" className="form-input card-input" value={text} disabled={disabled}
               onChange={(e) => onChange(e.target.value)} />
      )}
      {field.max_len && (
        <span className={`char-count ${text.length > field.max_len ? "over" : ""}`}>
          {text.length}/{field.max_len}
        </span>
      )}
    </div>
  );
}

// ─── Card editor (modal) ───────────────────────────────────────────────────

export function HpcCardEditor({ api, stage, studentId, studentName, onClose, onSubmitted }: {
  api: CardsApi;
  stage: string;
  studentId: string;
  studentName: string;
  onClose: () => void;
  onSubmitted: (studentId: string, status: string) => void;
}) {
  const [card, setCard] = useState<CardData | null>(null);
  const [values, setValues] = useState<Record<string, FieldValue>>({});
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [editedSinceCheck, setEditedSinceCheck] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{ status: string; errors: string[]; saved_parts: string[] } | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [activePart, setActivePart] = useState<string>("");

  const version = useRef<number | null>(null);
  const pending = useRef<Record<string, FieldValue>>({});
  const timer = useRef<number | undefined>(undefined);
  const inFlight = useRef<Promise<void> | null>(null);
  const partRefs = useRef<Record<string, HTMLElement | null>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await call<CardData>(api, "GET", cardPath(stage, studentId));
      setCard(data);
      setValues(Object.fromEntries(data.parts.flatMap((p) => p.fields.map((f) => [f.key, f.value]))));
      version.current = data.draft?.version ?? 0;
      setSavedAt(data.draft?.saved_at ?? null);
      setSaveState("idle");
      setEditedSinceCheck(false);
      setActivePart((cur) => cur || data.parts[0]?.code || "");
    } catch (e: any) {
      setLoadError(e.message);
    } finally {
      setLoading(false);
    }
  }, [api, stage, studentId]);

  useEffect(() => { load(); }, [load]);

  // Saves pending edits; resolves to false when they could not be saved.
  const flush = useCallback(async (): Promise<boolean> => {
    window.clearTimeout(timer.current);
    if (inFlight.current) await inFlight.current;
    const batch = pending.current;
    if (Object.keys(batch).length === 0) return true;
    pending.current = {};
    setSaveState("saving");
    const run = (async () => {
      try {
        const res = await call<{ version: number; saved_at: string; problems: Record<string, string> }>(
          api, "PUT", `${cardPath(stage, studentId)}/draft`, { values: batch, base_version: version.current });
        version.current = res.version;
        setSavedAt(res.saved_at);
        setProblems((prev) => {
          const next = { ...prev };
          for (const k of Object.keys(batch)) delete next[k];
          return { ...next, ...res.problems };
        });
        setSaveState(Object.keys(pending.current).length ? "pending" : "saved");
        return true;
      } catch (e: any) {
        pending.current = { ...batch, ...pending.current };   // keep the edits so nothing is lost
        setSaveState(e instanceof ApiError && e.status === 409 ? "conflict" : "error");
        return false;
      }
    })();
    inFlight.current = run.then(() => undefined);
    const ok = await run;
    inFlight.current = null;
    return ok;
  }, [api, stage, studentId]);

  const setValue = (key: string, v: FieldValue) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    pending.current = { ...pending.current, [key]: v };
    setSaveState("pending");
    setEditedSinceCheck(true);
    setSubmitResult(null);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 1200);
  };

  // Save what is left when the editor closes or the tab is closed.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (Object.keys(pending.current).length) { e.preventDefault(); e.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const close = async () => {
    if (!(await flush()) && !window.confirm("Your latest edits could not be saved. Close anyway and lose them?")) return;
    onClose();
  };

  const recheck = async () => {
    await flush();
    await load();
  };

  const discard = async () => {
    if (!window.confirm("Discard all unsubmitted changes to this card? The values saved on the PARAKH portal stay as they are.")) return;
    window.clearTimeout(timer.current);
    pending.current = {};
    try {
      await call(api, "DELETE", `${cardPath(stage, studentId)}/draft`);
      setProblems({});
      await load();
    } catch (e: any) {
      setLoadError(e.message);
    }
  };

  const submit = async () => {
    if (!window.confirm(`Save ${card?.student.student_name || studentName}'s card to the PARAKH portal and mark it complete?`)) return;
    if (!(await flush())) return;
    setSubmitting(true);
    setSubmitResult(null);
    try {
      const res = await call<{ status: string; errors: string[]; saved_parts: string[] }>(
        api, "POST", `${cardPath(stage, studentId)}/submit`);
      setSubmitResult(res);
      onSubmitted(studentId, res.status);
      await load();
    } catch (e: any) {
      setSubmitResult({ status: "FAILED", errors: [e.message], saved_parts: [] });
    } finally {
      setSubmitting(false);
    }
  };

  const jumpTo = (code: string) => {
    setActivePart(code);
    partRefs.current[code]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const changedCount = card
    ? card.parts.reduce((n, p) => n + p.fields.filter((f) => !sameValue(values[f.key], f.portal_value)).length, 0)
    : 0;

  const saveLabel = {
    idle: savedAt ? `Draft saved ${timeOf(savedAt)}` : "No unsaved changes",
    pending: "Unsaved changes…",
    saving: "Saving draft…",
    saved: `Draft saved ${savedAt ? timeOf(savedAt) : ""}`,
    conflict: "Changed in another window",
    error: "Draft not saved",
  }[saveState];

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="modal-dialog card-editor" role="dialog" aria-label={`HPC card of ${studentName}`}>
        <div className="modal-header card-editor-header">
          <div style={{ minWidth: 0 }}>
            <div className="modal-title">{card?.student.student_name || studentName}</div>
            <div className="card-editor-sub">
              {stage} Stage
              {card && <> · {card.student.grade} · Sec {card.student.section} · Session {card.session.label}</>}
              {card?.student.apaar_id && <> · APAAR <span className="mono-chip">{card.student.apaar_id}</span></>}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <span className={`save-indicator ${saveState}`}>
              {saveState === "saving" ? <RefreshCw size={13} className="spin" /> :
               saveState === "conflict" || saveState === "error" ? <AlertCircle size={13} /> :
               saveState === "pending" ? <Clock size={13} /> : <Save size={13} />}
              {saveLabel}
            </span>
            <button type="button" className="icon-btn" onClick={close} title="Close (unsaved changes are saved first)">
              <X size={18} />
            </button>
          </div>
        </div>

        {loading && !card ? (
          <div className="card-editor-empty">
            <RefreshCw size={32} className="spin" style={{ color: "var(--chakra-blue)" }} />
            <div style={{ fontWeight: 700 }}>Loading the card from PARAKH…</div>
            <div style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>The first card of a stage can take ~10 s while dropdown lists load.</div>
          </div>
        ) : loadError && !card ? (
          <div className="card-editor-empty">
            <AlertCircle size={32} color="var(--danger-500)" />
            <div style={{ fontWeight: 700 }}>Could not load this card</div>
            <div style={{ fontSize: "0.86rem", color: "var(--text-muted)", maxWidth: 480 }}>{loadError}</div>
            <button className="btn btn-outline" onClick={load}><RefreshCw size={14} /> Try again</button>
          </div>
        ) : card && (
          <div className="card-editor-layout">
            <nav className="card-part-nav" aria-label="Card parts">
              {card.parts.map((p) => (
                <button key={p.code} type="button" className={`card-part-link ${activePart === p.code ? "active" : ""}`}
                        onClick={() => jumpTo(p.code)}>
                  {p.complete ? <CheckCircle2 size={14} color="var(--green-500)" /> : <AlertCircle size={14} color="var(--kesari-600)" />}
                  <span>{p.title}</span>
                </button>
              ))}
              <div className="card-part-legend">
                {editedSinceCheck ? "Part status is from before your latest edits." : "Part status is up to date."}
                <button type="button" className="portal-link-btn" onClick={recheck} disabled={loading}>
                  <RefreshCw size={12} className={loading ? "spin" : ""} /> Check again
                </button>
              </div>
            </nav>

            <div className="card-editor-body">
              {saveState === "conflict" && (
                <div className="alert-box alert-warning">
                  <AlertCircle size={18} />
                  <div>
                    This card was changed in another tab or window, so your latest edits were not saved.{" "}
                    <button type="button" className="portal-link-btn" onClick={() => { pending.current = {}; load(); }}>Reload the card</button>
                    {" "}to continue (your unsaved edits here will be lost).
                  </div>
                </div>
              )}
              {saveState === "error" && (
                <div className="alert-box alert-error">
                  <AlertCircle size={18} />
                  <div>The draft could not be saved. <button type="button" className="portal-link-btn" onClick={flush}>Retry</button></div>
                </div>
              )}
              {submitResult && (
                <div className={`alert-box ${submitResult.status === "COMPLETED" ? "alert-success" : "alert-error"}`}>
                  {submitResult.status === "COMPLETED" ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                  <div>
                    <b>{submitResult.status === "COMPLETED" ? "Saved to PARAKH and marked complete." : `Submit status: ${submitResult.status.replace("_", " ")}`}</b>
                    {submitResult.saved_parts.length > 0 && <div style={{ fontSize: "0.84rem" }}>Parts saved: {submitResult.saved_parts.join(", ")}</div>}
                    {submitResult.errors.length > 0 && (
                      <ul className="problem-list">{submitResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                    )}
                  </div>
                </div>
              )}

              {card.parts.map((p) => (
                <section key={p.code} className="card-part" ref={(el) => { partRefs.current[p.code] = el; }}>
                  <div className="card-part-head">
                    <h3>{p.title}</h3>
                    <span className={`status-tag ${p.complete ? "completed" : "in-progress"}`}>
                      {p.complete ? <><CheckCircle2 size={12} /> Ready</> : <>{p.problems.length} to fix</>}
                    </span>
                  </div>
                  {p.problems.length > 0 && (
                    <ul className="problem-list part-problems">{p.problems.map((e, i) => <li key={i}>{e}</li>)}</ul>
                  )}
                  {!!p.warnings?.length && (
                    <ul className="problem-list part-warnings" aria-label="Check these">
                      {p.warnings.map((e, i) => <li key={i}>{e}</li>)}</ul>
                  )}
                  <div className="card-fields">
                    {p.fields.map((f) => {
                      const v = values[f.key];
                      const changed = !sameValue(v, f.portal_value);
                      const wide = f.multiple || (f.kind === "text" && (f.max_len === null || f.max_len > 80));
                      return (
                        <div key={f.key} className={`card-field ${wide ? "wide" : ""} ${problems[f.key] ? "has-problem" : ""}`}>
                          <label className="form-label">
                            {f.label}{f.required && <span className="req" title="Required">*</span>}
                            {changed && <span className="changed-dot" title={`On PARAKH: ${Array.isArray(f.portal_value) ? f.portal_value.join(", ") : f.portal_value || "(blank)"}`}>edited</span>}
                          </label>
                          <FieldInput field={f} value={v} onChange={(nv) => setValue(f.key, nv)} disabled={submitting} />
                          {f.from_records === "levels" && (f.from_levels
                            ? f.from_levels !== v && (
                              <button type="button" className="btn btn-outline btn-sm" disabled={submitting}
                                      onClick={() => setValue(f.key, f.from_levels!)}
                                      title={f.from_levels}>Write from this subject's levels</button>)
                            : <div className="form-hint">Tick all three levels to write this note from them.</div>)}
                          {problems[f.key] && <div className="field-problem">{problems[f.key]}</div>}
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          </div>
        )}

        {card && (
          <div className="modal-footer card-editor-footer">
            <span style={{ marginRight: "auto", fontSize: "0.84rem", color: "var(--text-muted)" }}>
              {changedCount > 0 ? `${changedCount} field(s) differ from PARAKH` : "Matches what is on PARAKH"}
              {card.student.completed && " · Card marked complete on PARAKH"}
            </span>
            <button className="btn btn-outline" onClick={discard} disabled={submitting || (!card.draft && changedCount === 0)}>
              <Trash2 size={15} /> Discard draft
            </button>
            <button className="btn btn-outline" onClick={async () => { await flush(); setShowPreview(true); }}>
              <Eye size={15} /> Preview
            </button>
            <button className="btn btn-green" onClick={submit}
                    disabled={submitting || saveState === "conflict" || (!card.ready && !editedSinceCheck)}
                    title={!card.ready && !editedSinceCheck ? "Fix the parts marked 'to fix' first" : "Save every part to the PARAKH portal"}>
              {submitting ? <RefreshCw size={15} className="spin" /> : <Sparkles size={15} />}
              {submitting ? "Submitting…" : "Submit to PARAKH"}
            </button>
          </div>
        )}
      </div>

      {showPreview && (
        <HpcCardPreview api={api} stage={stage} studentId={studentId} onClose={() => setShowPreview(false)} />
      )}
    </div>
  );
}

// ─── Print preview ─────────────────────────────────────────────────────────

function HpcCardPreview({ api, stage, studentId, onClose }: {
  api: CardsApi;
  stage: string;
  studentId: string;
  onClose: () => void;
}) {
  const [includeDraft, setIncludeDraft] = useState(true);
  const [data, setData] = useState<PreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    call<PreviewData>(api, "GET", `${cardPath(stage, studentId)}/preview?include_draft=${includeDraft}`)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [api, stage, studentId, includeDraft]);

  return (
    <div className="modal-overlay preview-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-dialog preview-dialog">
        <div className="modal-header no-print">
          <div className="modal-title">Card preview</div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
              <input type="checkbox" checked={includeDraft} onChange={(e) => setIncludeDraft(e.target.checked)} />
              Include unsubmitted changes
            </label>
            <button className="btn btn-primary" style={{ padding: "0.45rem 0.9rem" }} onClick={() => window.print()} disabled={!data}>
              <Printer size={15} /> Print
            </button>
            <button type="button" className="icon-btn" onClick={onClose} title="Close"><X size={18} /></button>
          </div>
        </div>
        <div className="modal-body preview-body print-area">
          {error ? (
            <div className="alert-box alert-error"><AlertCircle size={18} /> {error}</div>
          ) : !data ? (
            <div className="card-editor-empty"><RefreshCw size={28} className="spin" style={{ color: "var(--chakra-blue)" }} /> Loading preview…</div>
          ) : (
            <>
              <header className="preview-head">
                <div>
                  <h2>{data.student.student_name}</h2>
                  <div>{data.student.stage} Stage · {data.student.grade} · Section {data.student.section}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div>Holistic Progress Card</div>
                  <div>Session {data.session.label}</div>
                  {data.includes_draft && <div className="preview-draft-note">Includes changes not yet on PARAKH</div>}
                </div>
              </header>
              {data.sections.map((s) => (
                <section key={s.code} className="preview-section">
                  <h3>{s.title}{!s.complete && <span className="preview-incomplete"> (incomplete)</span>}</h3>
                  {s.items.length === 0 ? (
                    <p className="preview-blank">Nothing filled in yet.</p>
                  ) : (
                    <dl>
                      {s.items.map((it, i) => (
                        <Fragment key={i}><dt>{it.label}</dt><dd>{it.value}</dd></Fragment>
                      ))}
                    </dl>
                  )}
                </section>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Bulk entry: one field for the whole class ─────────────────────────────

// Common answers (tab 3) shows A1-A4 and Part C's remarks (its levels have their own grid); the Activities tab
// shows Part B's answers with the same tools.
export function HpcBulkEntry({ api, stage, parts: only = ["A1", "A2", "A3", "A4", "C"], title = "Class-wide answers", intro }: {
  api: CardsApi; stage: string; parts?: string[]; title?: string; intro?: React.ReactNode;
}) {
  const [parts, setParts] = useState<{ code: string; title: string; fields: FieldMeta[] }[]>([]);
  const [fieldKey, setFieldKey] = useState("");
  const [field, setField] = useState<(FieldMeta & { part_title: string }) | null>(null);
  const [rows, setRows] = useState<BulkRow[]>([]);
  const [readAt, setReadAt] = useState<string | null>(null);   // when the app's copy was read from PARAKH
  const [offline, setOffline] = useState(false);               // PARAKH not connected
  const [changedOnParakh, setChangedOnParakh] = useState<string[]>([]);
  const editsRef = useRef<Record<string, FieldValue>>({});
  const fieldRef = useRef("");
  const [edits, setEdits] = useState<Record<string, FieldValue>>({});
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [fillValue, setFillValue] = useState<FieldValue>("");
  const [loadingFields, setLoadingFields] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);
  // per question: how many students have an answer, so done and pending questions can be told apart
  const [progress, setProgress] = useState<{ total: number; fields: Record<string, { filled: number; required: boolean }> } | null>(null);

  // only the parts this stage has, once its questions are known (Foundational has no A3/A4, Preparatory no A4)
  const partCodes = parts.map((p) => p.code).join(",");
  const loadProgress = useCallback(async () => {
    if (!partCodes) return;
    try {
      const all = await Promise.all(partCodes.split(",").map((code) => call<{ total: number; fields: Record<string, { filled: number; required: boolean }> }>(
        api, "GET", `/teacher/hpc-cards/${encodeURIComponent(stage)}/progress?part=${encodeURIComponent(code)}`).catch(() => null)));
      const got = all.filter(Boolean) as { total: number; fields: Record<string, { filled: number; required: boolean }> }[];
      if (got.length) setProgress({ total: got[0].total, fields: Object.assign({}, ...got.map((g) => g.fields)) });
    } catch { /* the marks are a help only */ }
  }, [api, stage, partCodes]);

  useEffect(() => { loadProgress(); }, [loadProgress]);

  const status = (key: string) => {
    const p = progress?.fields[key];
    if (!p || !progress) return "";
    const left = progress.total - p.filled;
    return left <= 0 ? " — ✓ done" : ` — ${left} to fill${p.required ? " (required)" : ""}`;
  };

  useEffect(() => {
    let live = true;
    setLoadingFields(true);
    setParts([]);
    setFieldKey("");
    setField(null);
    setRows([]);
    setMessage(null);
    call<{ parts: { code: string; title: string; fields: FieldMeta[] }[] }>(api, "GET", `/teacher/hpc-cards/${encodeURIComponent(stage)}/fields?common=true`)
      .then((d) => {
        if (!live) return;
        setParts(d.parts.filter((p) => only.includes(p.code))
          .map((p) => (p.code === "C" ? { ...p, fields: p.fields.filter((f) => f.kind === "text") } : p))   // C levels: own grid
          .filter((p) => p.fields.length));
      })
      .catch((e) => { if (live) { if (needsParakh(e)) setOffline(true); else setMessage({ type: "error", text: e.message }); } })
      .finally(() => { if (live) setLoadingFields(false); });
    return () => { live = false; };
  }, [api, stage]);

  const loadRows = useCallback(async (key: string, refresh = false) => {
    setLoadingRows(true);
    setMessage(null);
    setEdits({});
    setProblems({});
    try {
      const d = await call<{ field: FieldMeta & { part_title: string }; rows: BulkRow[]; read_at?: string | null }>(
        api, "GET", `/teacher/hpc-cards/${encodeURIComponent(stage)}/bulk?field=${encodeURIComponent(key)}${refresh ? "&refresh=true" : ""}`);
      setField(d.field);
      setRows(d.rows);
      setReadAt(d.read_at || null);
      setFillValue(d.field.multiple ? [] : "");
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
      setRows([]);
    } finally {
      setLoadingRows(false);
    }
  }, [api, stage]);

  const pick = (key: string) => {
    if (Object.keys(edits).length && !window.confirm("Drop the changes you have not saved for this field?")) return;
    setFieldKey(key);
    if (key) loadRows(key); else { setField(null); setRows([]); }
  };

  useEffect(() => { editsRef.current = edits; fieldRef.current = fieldKey; });
  const checking = useCardCheck(api, stage, !!field, (ids) => {
    if (Object.keys(editsRef.current).length) setChangedOnParakh(ids);
    else if (fieldRef.current) loadRows(fieldRef.current).then(() => setMessage({ type: "success",
      text: `Updated from PARAKH: ${ids.length} student${ids.length === 1 ? "'s card was" : "s' cards were"} changed there.` }));
  });

  const valueOf = (r: BulkRow) => (r.student_id in edits ? edits[r.student_id] : r.value);

  const fillEmpty = () => {
    if (isBlank(fillValue)) return;
    const next = { ...edits };
    for (const r of rows) if (isBlank(valueOf(r))) next[r.student_id] = fillValue;
    setEdits(next);
  };
  // every student's answer replaced (e.g. new observations for a class that already has old ones); nothing is
  // saved until Save, and single students can still be changed first
  const fillAll = () => {
    if (isBlank(fillValue)) return;
    setEdits(Object.fromEntries(rows.map((r) => [r.student_id, fillValue])));
  };
  // what "Mix" hands out: a text answer's suggestions, or a single-choice question's options (Yes / No / Not sure);
  // a question where several options can be picked is not mixed
  const mixPool = !field || field.mixable === false ? []
    : field.suggestions?.length ? field.suggestions : !field.multiple ? field.options : field.mix_pool || [];
  // handed out at random, each used about equally (a shuffled round, again and again), so the class does not all
  // get the same answer; replaces every answer, saved only with Save
  const mixSuggestions = () => {
    const pool = mixPool;
    if (!pool.length) return;
    let round: string[] = [];
    const next = () => {
      if (!round.length) {
        round = [...pool];
        for (let i = round.length - 1; i > 0; i--) {             // Fisher-Yates
          const j = Math.floor(Math.random() * (i + 1));
          [round[i], round[j]] = [round[j], round[i]];
        }
      }
      return round.pop()!;
    };
    // a several-option question: a few different options per student, in the question's own order
    const value = (): FieldValue => {
      if (!field?.multiple) return next();
      const chosen = new Set<string>();
      while (chosen.size < (field.mix_pick || 1)) chosen.add(next());
      return field.options.filter((o) => chosen.has(o));
    };
    setEdits(Object.fromEntries(rows.map((r) => [r.student_id, value()])));
  };

  const save = async () => {
    const changed = Object.fromEntries(rows
      .filter((r) => r.student_id in edits && !sameValue(edits[r.student_id], r.value))
      .map((r) => [r.student_id, edits[r.student_id]]));
    if (!Object.keys(changed).length) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await call<{ saved: string[]; problems: Record<string, string> }>(
        api, "PUT", `/teacher/hpc-cards/${encodeURIComponent(stage)}/bulk`, { field: fieldKey, values: changed });
      setProblems(res.problems);
      setRows((prev) => prev.map((r) => res.saved.includes(r.student_id) ? { ...r, value: changed[r.student_id], in_draft: true } : r));
      setEdits((prev) => Object.fromEntries(Object.entries(prev).filter(([id]) => !res.saved.includes(id))));
      loadProgress();
      const bad = Object.keys(res.problems).length;
      setMessage({
        type: bad ? "warning" : "success",
        text: `Saved to ${res.saved.length} student draft(s).${bad ? ` ${bad} value(s) were not valid and were not saved.` : ""} Open each card and submit it to send the values to PARAKH.`,
      });
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const dirty = rows.filter((r) => r.student_id in edits && !sameValue(edits[r.student_id], r.value)).length;

  // "Mix all questions": every question on this screen at once, mixed answers, one save
  type MixResult = { applied: boolean; students: number; cells: number; fields: { key: string; label: string; filled: number }[];
                     skipped: { key: string; label: string; reason: string }[] };
  const [mixReplace, setMixReplace] = useState(false);
  const [mixPreview, setMixPreview] = useState<MixResult | null>(null);
  const [mixing, setMixing] = useState(false);
  const mixAll = async (apply: boolean) => {
    if (apply && dirty && !window.confirm("Drop the changes you have not saved for this question?")) return;
    setMixing(true);
    setMessage(null);
    try {
      const res = await call<MixResult>(api, "POST", `/teacher/hpc-cards/${encodeURIComponent(stage)}/bulk-mix`,
        { fields: parts.flatMap((p) => p.fields.map((f) => f.key)), replace: mixReplace, apply });
      if (apply) {
        setMixPreview(null);
        setMessage({ type: "success", text: `Saved ${res.cells} mixed answer${res.cells === 1 ? "" : "s"} for ${res.students} student${res.students === 1 ? "" : "s"}.` });
        loadProgress();
        if (fieldKey) loadRows(fieldKey);
      } else {
        setMixPreview(res);
      }
    } catch (e: any) {
      setMessage({ type: "error", text: e.message });
    } finally {
      setMixing(false);
    }
  };

  if (offline) return <div className="ui-panel"><ConnectPrompt what="your class's answers" /></div>;

  return (
    <div className="ui-panel">
      <div className="panel-header">
        <div className="panel-title"><Layers size={20} color="#CF4A0A" /><span>{title}</span></div>
      </div>
      <p className="form-hint" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
        {intro ?? <>Answers where most of the class has the same choice and only a few differ: mother tongue, the
          Yes/Sometimes/No questions, "all about me", goals and ambition, resources and support, and each subject's Part C
          note (written from that student's own levels for the subject - never a shared sentence). Each question says how many students are left. Use "Fill empty with" for
          the usual answer, "Apply to all" to replace every answer, or <b>Mix</b> to give students different suggested
          answers; change the few who differ, and save. Text boxes offer <b>Suggestions…</b>. Answers are pre-filled in the
          Excel file you download on tab 5, where you can still change any student. Medium of instruction and rural/urban
          are on tab 4 (Class settings); Part B's activities and answers are on tab 2 (Activities).</>}
      </p>

      {parts.length > 0 && (
        <div className="bulk-mixall" aria-live="polite">
          <button type="button" className="btn btn-outline" onClick={() => mixAll(false)} disabled={mixing || saving}>
            {mixing ? <RefreshCw size={15} className="spin" /> : <Layers size={15} />} Mix all questions
          </button>
          <label className="lib-radio">
            <input type="checkbox" checked={mixReplace} onChange={(e) => { setMixReplace(e.target.checked); setMixPreview(null); }} />
            Replace answers already filled
          </label>
          {mixPreview && (
            <div className="alert-box alert-info lib-inline-alert">
              <div>
                {mixPreview.cells === 0
                  ? <>Nothing to fill: every question already has an answer{mixReplace ? "" : " (tick 'Replace answers already filled' to mix them again)"}.</>
                  : <>Fills <b>{mixPreview.cells}</b> answers in <b>{mixPreview.fields.filter((f) => f.filled).length}</b> questions
                      for <b>{mixPreview.students}</b> students, each with one of the suggested answers at random
                      (Part C notes: written from each student's levels).</>}
                {mixPreview.skipped.length > 0 && (
                  <> Not mixed (fill them yourself): {mixPreview.skipped.map((x) => `${x.label} - ${x.reason}`).join("; ")}.</>
                )}
                {mixPreview.cells > 0 && (
                  <div style={{ marginTop: "0.5rem" }}>
                    <button type="button" className="btn btn-green" onClick={() => mixAll(true)} disabled={mixing}>
                      <Save size={15} /> Save all
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="bulk-toolbar">
        <select className="form-select" value={fieldKey} onChange={(e) => pick(e.target.value)} disabled={loadingFields || saving}>
          <option value="">{loadingFields ? "Loading fields…" : "— Choose a field —"}</option>
          {parts.map((p) => (
            <optgroup key={p.code} label={p.title}>
              {p.fields.map((f) => <option key={f.key} value={f.key}>{f.label}{status(f.key)}</option>)}
            </optgroup>
          ))}
        </select>
        {field && rows.length > 0 && field.from_records === "levels" && (
          <div className="bulk-fill">
            <span className="form-hint">Each student's note is written from their own three levels for this subject
              ({rows.filter((r) => !r.from_levels).length} without all three levels stay blank).</span>
            <button className="btn btn-outline" style={{ padding: "0.5rem 0.9rem" }}
                    onClick={() => setEdits({ ...edits, ...Object.fromEntries(rows.filter((r) => r.from_levels && isBlank(valueOf(r)))
                      .map((r) => [r.student_id, r.from_levels!])) })}
                    title="Fills only the students whose note is empty">Write empty notes from levels</button>
            <button className="btn btn-outline" style={{ padding: "0.5rem 0.9rem" }}
                    onClick={() => setEdits({ ...edits, ...Object.fromEntries(rows.filter((r) => r.from_levels)
                      .map((r) => [r.student_id, r.from_levels!])) })}
                    title="Writes every note again from the levels (saved only when you press Save)">Write all from levels</button>
          </div>
        )}
        {field && rows.length > 0 && field.from_records !== "levels" && (
          <div className="bulk-fill">
            <span className="form-label" style={{ whiteSpace: "nowrap" }}>Fill empty with</span>
            <FieldInput field={field} value={fillValue} onChange={setFillValue} compact />
            <button className="btn btn-outline" style={{ padding: "0.5rem 0.9rem" }} onClick={fillEmpty} disabled={isBlank(fillValue)}
                    title="Fills only the students whose answer is empty">Apply</button>
            <button className="btn btn-outline" style={{ padding: "0.5rem 0.9rem" }} onClick={fillAll} disabled={isBlank(fillValue)}
                    title="Replaces every student's answer (saved only when you press Save)">Apply to all</button>
            {mixPool.length > 1 && (
              <button className="btn btn-outline" style={{ padding: "0.5rem 0.9rem" }} onClick={mixSuggestions}
                      title={`Gives each student one of the ${field.suggestions?.length ? "suggestions" : "answers"} at random (saved only when you press Save)`}>
                {field.suggestions?.length ? "Mix suggestions" : "Mix answers"}
              </button>
            )}
          </div>
        )}
      </div>

      {message && (
        <div className={`alert-box alert-${message.type}`}>
          {message.type === "success" ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />} {message.text}
        </div>
      )}

      {loadingRows ? (
        <div className="card-editor-empty">
          <RefreshCw size={30} className="spin" style={{ color: "var(--chakra-blue)" }} />
          <div style={{ fontWeight: 700 }}>Loading this field for every student…</div>
          <div style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>The first time, each card is read from PARAKH (a large class can take a minute); after that it loads from the app.</div>
        </div>
      ) : field && (
        <>
          <div className="bulk-readat" aria-live="polite">
            {readAt && <span className="lib-muted">Loaded from the app's copy, read from PARAKH on {new Date(readAt).toLocaleString()}.</span>}
            {checking && <span className="lib-muted">Checking PARAKH for changes… ({checking.done} of {checking.total})</span>}
            <button type="button" className="portal-link-btn" onClick={() => loadRows(fieldKey, true)}
                    disabled={saving || Object.keys(edits).length > 0}>Read again from PARAKH</button>
          </div>
          {changedOnParakh.length > 0 && (
            <div className="alert-box alert-warning">
              <AlertCircle size={18} /> Changed on PARAKH since your copy: {changedOnParakh.map((id) => rows.find((r) => r.student_id === id)?.student_name || id).join(", ")}.{" "}
              <button type="button" className="portal-link-btn" onClick={() => { setChangedOnParakh([]); loadRows(fieldKey); }}>Show the new values</button>
              {" "}(unsaved changes for this field will be lost; save them first to keep them).
            </div>
          )}
          <div className="data-table-wrapper">
            <table className="data-table bulk-table">
              <thead>
                <tr>
                  <th style={{ width: 45 }}>#</th>
                  <th>Student</th>
                  <th>On PARAKH</th>
                  <th>{field.label}{field.required && " *"}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const v = valueOf(r);
                  const edited = r.student_id in edits && !sameValue(edits[r.student_id], r.value);
                  return (
                    <tr key={r.student_id} className={edited ? "row-edited" : ""}>
                      <td style={{ color: "var(--text-light)", fontWeight: 600 }}>{i + 1}</td>
                      <td>
                        <div style={{ fontWeight: 700, color: "var(--chakra-navy)" }}>{r.student_name}</div>
                        <div style={{ fontSize: "0.74rem", color: "var(--text-light)" }}>{r.grade} · Sec {r.section}</div>
                      </td>
                      <td style={{ fontSize: "0.84rem", color: "var(--text-muted)", maxWidth: 220 }}>
                        {isBlank(r.portal_value) ? "—" : Array.isArray(r.portal_value) ? r.portal_value.join(", ") : r.portal_value}
                        {r.in_draft && <div className="changed-dot" style={{ marginLeft: 0 }}>draft differs</div>}
                      </td>
                      <td style={{ minWidth: 240 }}>
                        <FieldInput field={field} value={v} compact disabled={saving}
                                    onChange={(nv) => setEdits((prev) => ({ ...prev, [r.student_id]: nv }))} />
                        {problems[r.student_id] && <div className="field-problem">{problems[r.student_id]}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="bulk-footer">
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>{dirty ? `${dirty} unsaved change(s)` : "No unsaved changes"}</span>
            <button className="btn btn-outline" onClick={() => setEdits({})} disabled={!dirty || saving}>Undo changes</button>
            <button className="btn btn-green" onClick={save} disabled={!dirty || saving}>
              {saving ? <RefreshCw size={15} className="spin" /> : <Save size={15} />} {saving ? "Saving…" : `Save ${dirty || ""} to drafts`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
