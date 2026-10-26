import { useEffect, useRef, useState } from "react";
import { call } from "../api";
import type { Api } from "../api";

// Screens load from the app's stored copy of the cards; meanwhile the server checks that copy against PARAKH
// (started by the same load). This follows that check and calls onChanged with the students whose card was
// changed on PARAKH, once per check that finishes after the screen opened.

export interface CardCheck {
  id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  done: number;
  total: number;
  changed: string[];
  error: string | null;
  finished_at: string | null;
}

const POLL_MS = 2000;

export function useCardCheck(api: Api, stage: string, active: boolean, onChanged: (studentIds: string[]) => void) {
  const [check, setCheck] = useState<CardCheck | null>(null);
  const opened = useRef(0);                         // when the screen opened (set once the check is followed)
  const handled = useRef<Set<string>>(new Set());
  const changedRef = useRef(onChanged);
  useEffect(() => { changedRef.current = onChanged; });

  useEffect(() => {
    if (!active) return;
    if (!opened.current) opened.current = Date.now();
    let live = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const { check: c } = await call<{ check: CardCheck | null }>(api, "GET", `/teacher/hpc-cards/${encodeURIComponent(stage)}/check`);
        if (!live) return;
        setCheck(c);
        if (c?.status === "RUNNING") {
          timer = window.setTimeout(poll, POLL_MS);
          return;
        }
        const finished = c?.finished_at ? Date.parse(c.finished_at) : 0;
        if (c && c.status === "COMPLETED" && c.changed.length && finished >= opened.current - 5000 && !handled.current.has(c.id)) {
          handled.current.add(c.id);
          changedRef.current(c.changed);
        }
      } catch {
        /* the check is only a help: the screen keeps working from the stored copy */
      }
    };
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, [api, stage, active]);

  return check?.status === "RUNNING" ? check : null;
}
