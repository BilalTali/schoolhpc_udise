import { useEffect, useState } from "react";
import { Plug, RefreshCw } from "lucide-react";
import { openParakh } from "./parakhConnect";

// Shown instead of an error when a screen needs PARAKH and the app is not connected.

export function ConnectPrompt({ what }: { what: string }) {
  return (
    <div className="connect-prompt" role="status">
      <span className="connect-icon" aria-hidden="true"><Plug size={22} /></span>
      <h3>Connect to PARAKH to see {what}</h3>
      <p>This screen reads your class from PARAKH. Connect once with your PARAKH login and it stays connected while you work.</p>
      <button type="button" className="btn btn-primary" onClick={openParakh}>Connect to PARAKH</button>
    </div>
  );
}

/** While a class screen reads its students' cards from PARAKH: what is happening, for how long so far, and why. */
export function ReadingFromParakh({ what }: { what: string }) {
  const [since] = useState(() => Date.now());
  const [now, setNow] = useState(since);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const secs = Math.round((now - since) / 1000);
  return (
    <div className="reading-note" role="status" aria-live="polite">
      <RefreshCw size={18} className="spin" aria-hidden="true" />
      <div>
        <b>Reading {what} from PARAKH… {secs >= 3 ? `${secs}s` : ""}</b>
        <small>
          Only the cards not kept yet are read: the first time after connecting, or after an upload changed them, a big
          class takes up to a minute or two. After that this screen opens at once.
        </small>
      </div>
    </div>
  );
}
