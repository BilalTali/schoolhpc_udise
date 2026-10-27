import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, Files, RefreshCw } from "lucide-react";
import { ApiError, apiFetch, call } from "../api";
import type { Api } from "../api";

// One Excel file for all the teacher's stages: a sheet per stage. Each stage needs its class check and its
// class settings first; this card shows where each stage is and offers the one download.

interface StageCheck {
  job: { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; ready: number } | null;
  settings_complete: boolean;
  students: number;
}

const POLL_MS = 2000;

export function AllStagesDownload({ api, stages: assigned, onOpenSettings }: { api: Api; stages: string[]; onOpenSettings: (stage: string) => void }) {
  const [checks, setChecks] = useState<Record<string, StageCheck>>({});
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);                 // bumped to look again while a check runs
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const alive = useRef(true);

  const names = assigned.join(",");                    // the stage names, so a new array each render is harmless
  const refresh = useCallback(async () => {
    try {
      const entries = await Promise.all(names.split(",").filter(Boolean).map(async (st) => [st, await call<StageCheck>(api, "GET", `/teacher/template/${st}/check`)] as const));
      if (!alive.current) return;
      const next = Object.fromEntries(entries);
      setChecks(next);
      window.clearTimeout(timer.current);
      if (Object.values(next).some((c) => c.job?.status === "RUNNING")) timer.current = window.setTimeout(() => setTick((t) => t + 1), POLL_MS);
    } catch (e: any) {
      if (alive.current) setError(e.message);
    }
  }, [api, names]);

  useEffect(() => {
    alive.current = true;
    refresh();
    return () => { alive.current = false; window.clearTimeout(timer.current); };
  }, [refresh, tick]);

  const check = async (stage: string) => {
    setError(null);
    try {
      await call(api, "POST", `/teacher/template/${stage}/check`);
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const stages = assigned.filter((st) => (checks[st]?.students ?? 1) > 0);   // stages with no students are left out
  const ready = stages.length > 0 && stages.every((st) => checks[st]?.job?.status === "COMPLETED" && checks[st]?.settings_complete);
  const total = stages.reduce((n, st) => n + (checks[st]?.job?.ready || 0), 0);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch("/teacher/template/all/download", {}, api.base);
      if (res.status === 401) api.onUnauthorized();
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body?.detail || "The file could not be made.");
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "HPC_All_stages_template.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ui-panel all-stages" aria-labelledby="as-title">
      <div className="panel-header">
        <div className="panel-title"><Files size={20} aria-hidden="true" /><span id="as-title">All your stages in one file</span></div>
      </div>
      <p className="lib-muted">One Excel file with a sheet for each stage ({stages.join(", ")}). Each stage keeps its own Part B,
        Settings and Exceptions sheets. Upload the one file and everyone is synced.</p>
      <ul className="as-list">
        {stages.map((st) => {
          const c = checks[st];
          const job = c?.job;
          const state = !c ? "Loading…"
            : job?.status === "RUNNING" ? `Checking… ${job.done} of ${job.total}`
            : job?.status === "COMPLETED" ? `${job.ready} of ${job.total} ready`
            : job?.status === "FAILED" ? "The check stopped" : "Not checked yet";
          const ok = job?.status === "COMPLETED" && c?.settings_complete;
          return (
            <li key={st} className={ok ? "ok" : ""}>
              {ok ? <CheckCircle2 size={16} aria-hidden="true" /> : <AlertCircle size={16} aria-hidden="true" />}
              <b>{st}</b>
              <span>{state}</span>
              {c && !c.settings_complete && (
                <button type="button" className="portal-link-btn" onClick={() => onOpenSettings(st)}>Finish class settings</button>
              )}
              <button type="button" className="btn btn-outline btn-sm" onClick={() => check(st)} disabled={job?.status === "RUNNING"}>
                <RefreshCw size={13} aria-hidden="true" className={job?.status === "RUNNING" ? "spin" : ""} /> {job ? "Check again" : "Check"}
              </button>
            </li>
          );
        })}
      </ul>
      {error && <div className="alert-box alert-error lib-inline-alert" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      <div className="tp-row">
        <button type="button" className="btn btn-primary" onClick={download} disabled={!ready || busy || total === 0}>
          <Download size={15} aria-hidden="true" /> Download one file for all stages ({total} students)
        </button>
        {!ready && <span className="lib-muted">Check the class and finish the settings on every stage first.</span>}
      </div>
    </section>
  );
}
