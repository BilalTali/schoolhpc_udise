import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";

// "What the server is doing for me now": class checks, cards read from PARAKH in the background, re-checks, a running
// upload - each with its progress. Looks every 3 s while something runs, every 20 s otherwise.

interface Task { kind: "class_check" | "reading" | "rechecking" | "upload"; stage: string; done: number; total: number }

const WHAT: Record<Task["kind"], string> = {
  class_check: "Checking the class (for the Excel file)",
  reading: "Reading the class's cards from PARAKH",
  rechecking: "Checking the kept cards against PARAKH",
  upload: "Saving to PARAKH",
};

export function ServerActivity({ api }: { api: Api }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    const look = async () => {
      let next: Task[] = [];
      try {
        next = (await call<{ tasks: Task[] }>(api, "GET", "/teacher/activity")).tasks;
      } catch {
        next = [];                                   // the strip is a help: a failed look just shows nothing
      }
      if (!alive) return;
      setTasks(next);
      timer.current = window.setTimeout(look, next.length ? 3000 : 20000);
    };
    look();
    return () => { alive = false; window.clearTimeout(timer.current); };
  }, [api]);

  if (!tasks.length) return null;
  return (
    <div className="server-activity" role="status" aria-live="polite">
      <RefreshCw size={16} className="spin" aria-hidden="true" />
      <b>Server is working:</b>
      <ul>
        {tasks.map((t) => (
          <li key={`${t.kind}-${t.stage}`}>
            <span>{WHAT[t.kind]} · {t.stage}</span>
            <span className="sa-bar" aria-hidden="true"><span style={{ width: `${t.total ? Math.round((t.done / t.total) * 100) : 5}%` }} /></span>
            <span className="sa-count">{t.done} of {t.total}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
