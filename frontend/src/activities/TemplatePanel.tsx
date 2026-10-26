import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, RefreshCw } from "lucide-react";
import { ApiError, apiFetch, call } from "../api";
import type { Api } from "../api";
import { useConfirm } from "./useConfirm";

// "Download template (Part B complete students only)": checks the class (reads PARAKH only), then
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

  const check = async () => {
    setError(null);
    try {
      await call(api, "POST", `/teacher/template/${stage}/check`);
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const download = async (all: boolean) => {
    const job = status?.job;
    if (all && job) {
      const notReady = job.students.filter((s) => !s.ready).length;
      const ok = await confirm({ title: "Download with every student?", confirmLabel: "Download all",
        message: `${notReady} student${notReady === 1 ? " is" : "s are"} not ready. They will be marked in the Problems column, and on upload they will be skipped until their Part B is complete.` });
      if (!ok) return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/teacher/template/${stage}/download?include=${all ? "all" : "ready"}${all ? "&confirmed=true" : ""}`, {}, api.base);
      if (res.status === 401) api.onUnauthorized();
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body?.detail || "The file could not be made.");
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `HPC_${stage}_template${all ? "_all" : ""}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
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
  const minutes = Math.max(1, Math.round((total * 7) / 1.5 / 60));
  const why = !settingsOk ? "Finish the class settings first." : !job || job.status !== "COMPLETED" ? "Check the class first."
    : job.ready === 0 ? "No student's Part B is complete yet - see the list below." : "";

  return (
    <section className="tp" aria-labelledby="tp-title">
      <h3 id="tp-title" className="lib-section-title"><FileSpreadsheet size={18} aria-hidden="true" /> Download the Excel template</h3>
      <p className="lib-muted">The file has only the students whose Part B is complete, so the upload does not fail on students who are not ready. Part B and the class settings go in as locked sheets; you fill A1, A2{stage !== "Foundational" ? ", A3" : ""}{stage === "Middle" ? ", A4" : ""}, C{stage !== "Foundational" ? " and the marks obtained" : ""}.</p>

      {status && !settingsOk && (
        <div className="alert-box alert-warning lib-inline-alert">
          <AlertCircle size={18} aria-hidden="true" />
          <div>The class settings are not finished: {(status.settings_missing || []).join("; ")}.{" "}
            <button type="button" className="portal-link-btn" onClick={onOpenSettings}>Open Class settings</button></div>
        </div>
      )}

      <div className="tp-row">
        <button type="button" className="btn btn-outline" onClick={check} disabled={running}>
          <RefreshCw size={14} aria-hidden="true" className={running ? "spin" : ""} /> {job ? "Check the class again" : "Check the class"}
        </button>
        <span className="lib-muted">Reads each student's card from PARAKH (nothing is saved) – about {minutes} minute{minutes === 1 ? "" : "s"} for {total} students.</span>
      </div>

      <div aria-live="polite">
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
        <button type="button" className="btn btn-green" onClick={() => download(false)} disabled={!!why || busy}
                aria-describedby={why ? "tp-why" : undefined}>
          <Download size={15} aria-hidden="true" /> Download template ({job?.status === "COMPLETED" ? `${job.ready} of ${job.total}` : `? of ${total}`} students)
        </button>
        <button type="button" className="btn btn-outline" onClick={() => download(true)}
                disabled={!settingsOk || job?.status !== "COMPLETED" || busy}>
          Download template (all students)…
        </button>
        {why && <span id="tp-why" className="lib-muted">{why}</span>}
      </div>

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
