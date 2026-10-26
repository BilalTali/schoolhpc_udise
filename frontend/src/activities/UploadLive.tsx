import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, CircleDashed, Download, MinusCircle, RefreshCw } from "lucide-react";
import { apiFetch, call } from "../api";
import type { Api } from "../api";

// A live mirror of an upload while the server saves it to PARAKH: which student and step right now, every
// student's state, and a short timeline. Asks the server every second while the job runs.

interface LiveStudent { student_id: string; student_name: string; status: string; error: string | null }
interface LiveEvent { at: string; student_id: string; student_name: string; text: string; kind: "step" | "saved" | "failed" | "skipped" }
export interface LiveJob {
  job_id: string;
  status: string;
  total_students: number;
  success_count: number;
  failed_count: number;
  created_at: string;
  completed_at: string | null;
  current: { student_id: string; student_name: string; step: string; since: string } | null;
  events: LiveEvent[];
  students: LiveStudent[];
}

const POLL_MS = 1000;
const RUNNING = ["PENDING", "IN_PROGRESS"];
const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function UploadLive({ api, jobId, onFinished }: { api: Api; jobId: string; onFinished: (job: LiveJob) => void }) {
  const [job, setJob] = useState<LiveJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const finished = useRef<string | null>(null);
  const onFinishedRef = useRef(onFinished);
  useEffect(() => { onFinishedRef.current = onFinished; });

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const j = await call<LiveJob>(api, "GET", `/teacher/upload/jobs/${jobId}/live`);
        if (!live) return;
        setJob(j);
        setError(null);
        setNow(Date.now());
        if (RUNNING.includes(j.status)) {
          timer = window.setTimeout(poll, POLL_MS);
        } else if (finished.current !== j.job_id) {
          finished.current = j.job_id;
          onFinishedRef.current(j);
        }
      } catch (e: any) {
        if (!live) return;
        setError(e.message);
        timer = window.setTimeout(poll, POLL_MS * 3);          // the save goes on on the server; try again
      }
    };
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, [api, jobId]);

  if (!job) {
    return <div className="ul-card"><p className="lib-muted"><RefreshCw size={14} className="spin" aria-hidden="true" /> Starting…</p></div>;
  }

  const running = RUNNING.includes(job.status);
  const counts = { saved: 0, failed: 0, skipped: 0, working: 0, waiting: 0 };
  for (const s of job.students) counts[kindOf(s.status)]++;
  const done = counts.saved + counts.failed + counts.skipped;
  const total = job.students.length || job.total_students;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const elapsed = Math.max(0, Math.round(((job.completed_at ? Date.parse(job.completed_at + (job.completed_at.endsWith("Z") ? "" : "Z")) : now)
    - Date.parse(job.created_at + (job.created_at.endsWith("Z") ? "" : "Z"))) / 1000));
  const perStudent = done ? elapsed / done : 0;
  const left = running && perStudent ? Math.round(perStudent * (total - done)) : 0;

  return (
    <section className="ul-card" aria-labelledby="ul-title">
      <div className="ul-head">
        <h3 id="ul-title" className="lib-section-title">
          {running ? <RefreshCw size={16} className="spin" aria-hidden="true" /> : job.failed_count ? <AlertCircle size={16} color="#B91C1C" aria-hidden="true" />
            : <CheckCircle2 size={16} color="#15803D" aria-hidden="true" />}
          {running ? "Saving to PARAKH…" : job.failed_count ? "Finished, with some not saved" : "Finished: all saved to PARAKH"}
        </h3>
        <span className="lib-muted">{done} of {total} done · {fmt(elapsed)}{left ? ` · about ${fmt(left)} left` : ""}</span>
      </div>
      <div className="progress-bar-container" role="progressbar" aria-label="Students done" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
        <div className="progress-fill" style={{ width: `${pct}%`, transition: "width 0.5s ease" }} />
      </div>
      <div className="ul-counts">
        <span className="ul-chip ul-saved"><CheckCircle2 size={13} aria-hidden="true" /> {counts.saved} saved</span>
        <span className="ul-chip ul-failed"><AlertCircle size={13} aria-hidden="true" /> {counts.failed} not saved</span>
        <span className="ul-chip ul-skipped"><MinusCircle size={13} aria-hidden="true" /> {counts.skipped} skipped</span>
        <span className="ul-chip ul-waiting"><CircleDashed size={13} aria-hidden="true" /> {counts.waiting + counts.working} to go</span>
      </div>

      <div aria-live="polite" className="ul-now">
        {running && job.current && (
          <p><b>{job.current.student_name}</b> <span className="lib-muted">({job.current.student_id})</span> — {job.current.step}…</p>
        )}
        {running && !job.current && <p className="lib-muted">Getting the next student ready…</p>}
        {error && <p className="field-problem">Lost touch with the server for a moment ({error}); the save goes on and this view will catch up.</p>}
      </div>

      <div className="ul-grid">
        <table className="data-table ul-table">
          <caption className="sr-only">Every student in this upload and where they are</caption>
          <thead><tr><th scope="col">Student</th><th scope="col">ID</th><th scope="col">Now</th></tr></thead>
          <tbody>
            {job.students.map((s) => {
              const kind = kindOf(s.status);
              const isCurrent = job.current?.student_id === s.student_id;
              return (
                <tr key={s.student_id} className={isCurrent ? "ul-current" : ""}>
                  <td><b>{s.student_name}</b></td>
                  <td className="lib-muted">{s.student_id}</td>
                  <td>
                    <span className={`ul-chip ul-${kind}`}>{LABEL[kind]}</span>
                    {isCurrent && <span className="lib-muted"> {job.current!.step}</span>}
                    {kind === "failed" && s.error && <div className="field-problem">{s.error}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="ul-timeline">
          <h4>What happened</h4>
          <ol>
            {[...job.events].reverse().slice(0, 25).map((e, i) => (
              <li key={i} className={`ul-ev-${e.kind}`}>
                <span className="ul-time">{time(e.at)}</span> <b>{e.student_name}</b> — {e.text}
              </li>
            ))}
            {job.events.length === 0 && <li className="lib-muted">Nothing yet.</li>}
          </ol>
        </div>
      </div>

      {!running && (
        <div className="ul-actions">
          <button type="button" className="btn btn-outline" onClick={() => downloadReport(api, job.job_id)}>
            <Download size={14} aria-hidden="true" /> Download the report (CSV)
          </button>
        </div>
      )}
    </section>
  );
}

type Kind = "saved" | "failed" | "skipped" | "working" | "waiting";
const LABEL: Record<Kind, string> = { saved: "Saved", failed: "Not saved", skipped: "Skipped", working: "Working…", waiting: "Waiting" };

function kindOf(status: string): Kind {
  if (status === "SUCCESS") return "saved";
  if (status === "FAILED" || status === "INVALID") return "failed";
  if (status === "SKIPPED") return "skipped";
  if (status === "IN_PROGRESS") return "working";
  return "waiting";
}

function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m} min ${s} s` : `${s} s`;
}

async function downloadReport(api: Api, jobId: string) {
  const res = await apiFetch(`/teacher/upload/jobs/${jobId}/export`, {}, api.base);
  if (!res.ok) return;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `hpc_upload_${jobId.slice(0, 8)}_report.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
