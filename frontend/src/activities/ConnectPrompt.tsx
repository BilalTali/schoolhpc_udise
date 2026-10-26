import { Plug } from "lucide-react";
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
