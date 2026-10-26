import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, CloudDownload, RefreshCw } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";
import { formatWhen } from "./types";
import type { SyncJob } from "./types";

// "Get activities from PARAKH": starts a read-only sync and follows it until it ends.
// Polling stops as soon as the page is left (the sync itself keeps running on the server).

const POLL_MS = 1500;

export function SyncPanel({ api, stage, latest, lastSynced, onFinished }: {
  api: Api;
  stage: string;
  latest: SyncJob | null;
  lastSynced: Record<string, string>;
  onFinished: () => void;
}) {
  const [job, setJob] = useState<SyncJob | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const alive = useRef(true);
  const onFinishedRef = useRef(onFinished);
  useEffect(() => { onFinishedRef.current = onFinished; });

  const follow = (id: string) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        const next = await call<SyncJob>(api, "GET", `/activity-library/sync/${id}`);
        if (!alive.current) return;
        setJob(next);
        if (next.status === "COMPLETED" || next.status === "FAILED") onFinishedRef.current();
        else follow(id);
      } catch {
        if (alive.current) follow(id);            // a missed poll is retried; the sync is unaffected
      }
    }, POLL_MS);
  };

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);

  // A sync started earlier (or in another tab) that is still running: show and follow it.
  useEffect(() => {
    if (latest && (latest.status === "RUNNING" || latest.status === "QUEUED") && !job) {
      setJob(latest);
      follow(latest.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest?.id]);

  const start = async (allStages: boolean) => {
    setStarting(true);
    setStartError(null);
    try {
      const started = await call<SyncJob>(api, "POST", "/activity-library/sync", allStages ? {} : { stage });
      if (!alive.current) return;
      setJob(started);
      follow(started.id);
    } catch (e: any) {
      if (alive.current) setStartError(e.message);
    } finally {
      if (alive.current) setStarting(false);
    }
  };

  const running = job && (job.status === "RUNNING" || job.status === "QUEUED");
  const total = (k: "new" | "updated" | "removed") =>
    Object.values(job?.counts || {}).reduce((n, c) => n + (c?.[k] || 0), 0);

  return (
    <section className="lib-sync" aria-labelledby="lib-sync-title">
      <div className="lib-sync-head">
        <div>
          <h2 id="lib-sync-title" className="lib-section-title"><CloudDownload size={18} aria-hidden="true" /> Get activities from PARAKH</h2>
          <p className="lib-muted">
            Reads the PARAKH Activity Bank and keeps a copy here. Nothing is changed on PARAKH.
            {" "}{stage} last updated: <b>{formatWhen(lastSynced[stage])}</b>.
          </p>
        </div>
        <div className="lib-sync-buttons">
          <button type="button" className="btn btn-primary" onClick={() => start(false)} disabled={!!running || starting}>
            <RefreshCw size={15} aria-hidden="true" className={running ? "spin" : ""} /> Update {stage}
          </button>
          <button type="button" className="btn btn-outline" onClick={() => start(true)} disabled={!!running || starting}>
            Update all stages
          </button>
        </div>
      </div>

      <div aria-live="polite">
        {startError && (
          <div className="alert-box alert-error lib-inline-alert" role="alert">
            <AlertCircle size={18} aria-hidden="true" /> <div>{startError}</div>
          </div>
        )}
        {running && job && (
          <div className="lib-sync-progress">
            <div className="lib-sync-step">{job.step || "Starting…"}</div>
            <div className="progress-bar-container" role="progressbar" aria-label="Sync progress"
                 aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}>
              <div className="progress-fill" style={{ width: `${job.progress}%` }} />
            </div>
            {job.already_running && <div className="lib-muted">A sync for your school was already running, so this is that one.</div>}
          </div>
        )}
        {job?.status === "COMPLETED" && (
          <div className="alert-box alert-success lib-inline-alert">
            <CheckCircle2 size={18} aria-hidden="true" />
            <div>
              <b>Up to date.</b> {total("new")} new, {total("updated")} changed on PARAKH, {total("removed")} no longer on PARAKH
              {total("removed") > 0 && " (kept here and marked, because cards may already use them)"}.
            </div>
          </div>
        )}
        {job?.status === "FAILED" && (
          <div className="alert-box alert-error lib-inline-alert" role="alert">
            <AlertCircle size={18} aria-hidden="true" />
            <div><b>The update did not finish.</b> Your library was not changed. {job.error}</div>
          </div>
        )}
      </div>
    </section>
  );
}
