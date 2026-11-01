import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, RefreshCw } from "lucide-react";
import { ApiError, apiFetch, call } from "../api";
import type { Api } from "../api";
import { useConfirm } from "./useConfirm";
import { PrecheckView } from "./Precheck";
import type { PrecheckResult } from "./Precheck";

// "Download template (Part B complete students only)": checks the class (from the cards the app keeps), then
// offers the Excel with just the students whose Part B passes the real save's checks.

interface CheckStudent {
  student_id: string;
  student_name?: string;
  grade: string;
  section: string;
  ready: boolean;
  part_b_problems: string[];
  other_problems: string[];
  fix: "activities" | "card" | "";
}
interface CheckJob {
  id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  done: number;
  total: number;
  seconds_left: number;
  finished_at: string | null;
  error: string | null;
  ready: number;
  students: CheckStudent[];
}
interface CheckStatus { job: CheckJob | null; settings_complete: boolean; settings_missing: string[] }

const POLL_MS = 1500;
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");

export function TemplatePanel({ api, stage, total, onFix, onOpenSettings }: {
  api: Api;
  stage: string;
  total: number;
  onFix: (studentId: string, where: "activities" | "card", name: string) => void;
  onOpenSettings: () => void;
}) {
  const [status, setStatus] = useState<CheckStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);              // bumped to poll again while a check runs
  const [confirmUi, confirm] = useConfirm();
  const [pre, setPre] = useState<PrecheckResult | null>(null);   // empty answers found before the check
  const [preBusy, setPreBusy] = useState(false);
  const [picking, setPicking] = useState(false);              // "Download chosen students": the list is open
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [find, setFind] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const s = await call<CheckStatus>(api, "GET", `/teacher/template/${stage}/check`);
      if (!alive.current) return;
      setStatus(s);
      window.clearTimeout(timer.current);
      if (s.job?.status === "RUNNING") timer.current = window.setTimeout(() => setTick((t) => t + 1), POLL_MS);
    } catch (e: any) {
      if (alive.current) setError(e.message);
    }
  }, [api, stage]);

  useEffect(() => {
    alive.current = true;
    refresh();
    return () => { alive.current = false; window.clearTimeout(timer.current); };
  }, [refresh, tick]);

  // "Check": first every empty required answer from what the app holds, with where to fix it; the check itself
  // starts when there is nothing missing, or when the teacher starts it anyway
  const startCheck = async () => {
    setError(null);
    setPre(null);
    try {
      await call(api, "POST", `/teacher/template/${stage}/check`);
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };
  const check = async () => {
    setError(null);
    setPreBusy(true);
    try {
      const result = await call<PrecheckResult>(api, "GET", `/teacher/template/${stage}/precheck`);
      if (result.items.length) setPre(result);
      else await startCheck();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPreBusy(false);
    }
  };

  const download = async (all: boolean, ids?: string[]) => {
    const job = status?.job;
    if (all && job && !ids) {
      const notReady = job.students.filter((s) => !s.ready).length;
      const ok = await confirm({ title: "Download with every student?", confirmLabel: "Download all",
        message: `${notReady} student${notReady === 1 ? " is" : "s are"} not ready. They will be marked in the Problems column, and on upload they will be skipped until their Part B is complete.` });
      if (!ok) return;
    }
    setBusy(true);
    setError(null);
    try {
      const query = ids ? `students=${encodeURIComponent(ids.join(","))}`
        : `include=${all ? "all" : "ready"}${all ? "&confirmed=true" : ""}`;
      const res = await apiFetch(`/teacher/template/${stage}/download?${query}`, {}, api.base);
      if (res.status === 401) api.onUnauthorized();
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body?.detail || "The file could not be made.");
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `HPC_${stage}_template${ids ? "_chosen" : all ? "_all" : ""}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // the ready students straight to PARAKH: the server makes the class file, checks it against PARAKH exactly like
  // an upload, and saves it with the usual upload (its progress shows under Excel & upload)
  const [sent, setSent] = useState<string | null>(null);
  const send = async () => {
    const ready = status?.job?.ready ?? 0;
    const ok = await confirm({ title: "Save to PARAKH now?", confirmLabel: "Save to PARAKH",
      message: `The ${ready} ready student${ready === 1 ? "" : "s"} are checked against PARAKH and saved there, with what you chose in the app and the school's attendance and marks. A card that is not complete is not sent.` });
    if (!ok) return;
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      const r = await call<{ total_students: number }>(api, "POST", `/teacher/send/${stage}`);
      setSent(`Saving ${r.total_students} student${r.total_students === 1 ? "" : "s"} to PARAKH - the progress and any problems show in the upload list below.`);
      window.dispatchEvent(new CustomEvent("hpc-upload-started"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const job = status?.job;
  const running = job?.status === "RUNNING";
  const settingsOk = !!status?.settings_complete;
  const notReady = job?.status === "COMPLETED" ? job.students.filter((s) => !s.ready) : [];
  // Global Mix (emergency): every EMPTY answer of the class in one go - activities from the library (dealt across
  // students), levels, every class-wide question and Part C (notes from its levels). Facts and anything already
  // entered are kept. Preview first, then apply, then the class is checked.
  const [mixMsg, setMixMsg] = useState<string | null>(null);
  const globalMix = async () => {
    setError(null);
    setMixMsg(null);
    setBusy(true);
    try {
      type Mix = { seed: string; from_marks: number; grid: { cells: number; students: number; skipped: { student_name: string }[]; no_activity: string[] };
                   answers: { cells: number; students: number; skipped: { label: string; reason: string }[] } };
      const preview = await call<Mix>(api, "POST", `/teacher/activities-grid/${stage}/global-mix`, {});
      if (!preview.grid.cells && !preview.answers.cells) {
        setMixMsg("Nothing to mix: every answer that can be mixed is already filled.");
        return;
      }
      const notes = [preview.grid.skipped.length ? `${preview.grid.skipped.length} student(s) skipped (their activities on PARAKH share subjects)` : "",
                     preview.grid.no_activity.length ? `no library activity for: ${preview.grid.no_activity.join(", ")}` : ""].filter(Boolean);
      const ok = await confirm({ title: "Global Mix: fill every empty answer?", confirmLabel: "Mix and fill",
        message: `Fills ${preview.grid.cells} activity/level cells and ${preview.answers.cells} answers at random for the whole class. `
          + (preview.from_marks ? `${preview.from_marks} student(s) get their levels from the school's summative marks (75%+ Advanced, 50%+ Proficient, else Beginner); the rest at random. ` : "")
          + "Only empty answers are filled; nothing you entered changes. Mother tongue, names and other facts are not filled. "
          + "Use it only when there is no time to fill the cards properly." + (notes.length ? ` (${notes.join("; ")})` : "") });
      if (!ok) return;
      const done = await call<Mix>(api, "POST", `/teacher/activities-grid/${stage}/global-mix`, { apply: true, seed: preview.seed });
      setMixMsg(`Filled ${done.grid.cells} activity/level cells and ${done.answers.cells} answers. Checking the class now - then "Save ready students to PARAKH".`);
      await startCheck();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const why = !settingsOk ? "Finish the class settings first." : !job || job.status !== "COMPLETED" ? "Check the class first."
    : job.ready === 0 ? "No student's Part B is complete yet - see the list below." : "";

  return (
    <section className="tp" aria-labelledby="tp-title">
      <h3 id="tp-title" className="lib-section-title"><FileSpreadsheet size={18} aria-hidden="true" /> Download the Excel template</h3>
      <p className="lib-muted">The file has only the students whose Part B is complete, so the upload does not fail on students who are not ready. Part B goes in as a locked sheet; the class settings can be changed on the Settings sheet (the upload uses them and saves them here); you fill A1, A2{stage !== "Foundational" ? ", A3" : ""}{stage === "Middle" ? ", A4" : ""}, C{stage !== "Foundational" ? " and the marks obtained" : ""}.</p>

      {status && !settingsOk && (
        <div className="alert-box alert-warning lib-inline-alert">
          <AlertCircle size={18} aria-hidden="true" />
          <div>The class settings are not finished: {(status.settings_missing || []).join("; ")}.{" "}
            <button type="button" className="portal-link-btn" onClick={onOpenSettings}>Open Class settings</button></div>
        </div>
      )}

      <div className="tp-row">
        <button type="button" className="btn btn-outline" onClick={globalMix} disabled={running || preBusy || busy}
                title="Emergency: fills every empty answer of the class at random (activities, levels, A-C)">
          <RefreshCw size={14} aria-hidden="true" className={busy ? "spin" : ""} /> Global Mix (fill all empty)
        </button>
        <button type="button" className="btn btn-outline" onClick={check} disabled={running || preBusy}>
          <RefreshCw size={14} aria-hidden="true" className={running || preBusy ? "spin" : ""} />
          {preBusy ? " Looking for empty answers…" : job ? " Check the class again" : " Check the class"}
        </button>
        <span className="lib-muted">Uses the cards the app already keeps, so it takes seconds; only a student not read yet is read from PARAKH. Nothing is saved – the upload checks every student against PARAKH again.</span>
      </div>

      <div aria-live="polite">
        {pre && <PrecheckView result={pre} onStart={startCheck} onClose={() => setPre(null)} />}
        {running && job && (
          <div className="lib-sync-progress">
            <div className="lib-sync-step">Checking {job.done} of {job.total} students{job.seconds_left ? ` · about ${Math.ceil(job.seconds_left / 60)} min left` : ""}</div>
            <div className="progress-bar-container" role="progressbar" aria-label="Checking the class" aria-valuemin={0}
                 aria-valuemax={job.total} aria-valuenow={job.done}>
              <div className="progress-fill" style={{ width: `${job.total ? (job.done / job.total) * 100 : 0}%` }} />
            </div>
          </div>
        )}
        {job?.status === "FAILED" && <div className="alert-box alert-error lib-inline-alert" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{job.error}</div></div>}
        {job?.status === "COMPLETED" && (
          <p className="tp-summary"><CheckCircle2 size={16} color="#046A38" aria-hidden="true" /> Ready as of {time(job.finished_at)}: <b>{job.ready} of {job.total}</b> students have Part B complete.</p>
        )}
        {error && <div className="alert-box alert-error lib-inline-alert" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      </div>

      <div className="tp-row">
        <button type="button" className="btn btn-primary" onClick={send} disabled={!!why || busy}
                title="No Excel: the ready students go to PARAKH straight from what is chosen in the app">
          <CheckCircle2 size={15} aria-hidden="true" /> Save ready students to PARAKH ({job?.status === "COMPLETED" ? job.ready : "?"})
        </button>
        <button type="button" className="btn btn-green" onClick={() => download(false)} disabled={!!why || busy}
                aria-describedby={why ? "tp-why" : undefined}>
          <Download size={15} aria-hidden="true" /> Download template ({job?.status === "COMPLETED" ? `${job.ready} of ${job.total}` : `? of ${total}`} students)
        </button>
        <button type="button" className="btn btn-outline" onClick={() => download(true)}
                disabled={!settingsOk || job?.status !== "COMPLETED" || busy}>
          Download template (all students)…
        </button>
        <button type="button" className="btn btn-outline" onClick={() => setPicking((p) => !p)} aria-expanded={picking}
                disabled={!settingsOk || job?.status !== "COMPLETED" || busy}>
          Download chosen students…
        </button>
        {why && <span id="tp-why" className="lib-muted">{why}</span>}
        <button type="button" className="btn btn-outline" disabled={busy}
                onClick={async () => {
                  const res = await apiFetch("/teacher/register/report.xlsx", {}, api.base);
                  if (!res.ok) { setError("The report could not be made."); return; }
                  const url = URL.createObjectURL(await res.blob());
                  const a = document.createElement("a"); a.href = url; a.download = "My_students.xlsx"; a.click();
                  URL.revokeObjectURL(url);
                }}>
          <Download size={15} aria-hidden="true" /> My students report (Excel)
        </button>
      </div>
      {mixMsg && <p className="tp-summary" role="status"><CheckCircle2 size={16} color="#046A38" aria-hidden="true" /> {mixMsg}</p>}
      {sent && <p className="tp-summary" role="status"><CheckCircle2 size={16} color="#046A38" aria-hidden="true" /> {sent}</p>}

      {picking && job?.status === "COMPLETED" && (
        <div className="tp-pick" role="group" aria-label="Choose the students for the file">
          <div className="tp-pick-bar">
            <input type="search" className="form-input" placeholder="Find a name or ID" value={find}
                   onChange={(e) => setFind(e.target.value)} aria-label="Find a student" />
            <button type="button" className="btn btn-green" disabled={!picked.size || busy}
                    onClick={() => download(false, [...picked])}>
              <Download size={15} aria-hidden="true" /> Download {picked.size} chosen
            </button>
            {picked.size > 0 && <button type="button" className="btn btn-outline" onClick={() => setPicked(new Set())}>Clear</button>}
          </div>
          <ul>
            {job.students.filter((s) => `${s.student_name || ""} ${s.student_id}`.toLowerCase().includes(find.trim().toLowerCase()))
              .map((s) => (
                <li key={s.student_id}>
                  <label>
                    <input type="checkbox" checked={picked.has(s.student_id)}
                           onChange={(e) => setPicked((prev) => {
                             const next = new Set(prev);
                             if (e.target.checked) next.add(s.student_id); else next.delete(s.student_id);
                             return next;
                           })} />
                    {" "}<b>{s.student_name || "Student"}</b> · ID {s.student_id}{!s.ready && <span className="lib-muted"> · Part B not complete</span>}
                  </label>
                </li>
              ))}
          </ul>
        </div>
      )}

      {notReady.length > 0 && (
        <details className="tp-list" open={notReady.length <= 8}>
          <summary>Who is not ready ({notReady.length})</summary>
          <ul>
            {notReady.map((s) => (
              <li key={s.student_id}>
                <span><b>{s.student_name || "Student"}</b> · ID {s.student_id} · {s.part_b_problems.join("; ")}</span>
                {s.fix && (
                  <button type="button" className="btn btn-outline tp-fix" onClick={() => onFix(s.student_id, s.fix as "activities" | "card", s.student_name || "")}>
                    {s.fix === "activities" ? "Fix in Activities" : "Fix in the card"}<span className="sr-only"> for student {s.student_id}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {confirmUi}
    </section>
  );
}
