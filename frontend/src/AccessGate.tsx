import { useState } from "react";
import { AlertCircle, KeyRound, Lock } from "lucide-react";
import { apiFetch, errorText } from "./api";

// The portal's access key: shown before anything else while this browser has not entered the key the admin set.

export function AccessGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unlock = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch("/access/unlock", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }),
      });
      if (res.ok) {
        onUnlocked();
        return;
      }
      setError(errorText(await res.json().catch(() => ({}))));
    } catch {
      setError("Could not reach the server. Check that it is running and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page gate-page">
      <section className="auth-panel">
        <form className="auth-card gate-card" onSubmit={unlock}>
          <div className="gate-icon"><Lock size={26} aria-hidden="true" /></div>
          <h2>Enter the portal's access key</h2>
          <p className="auth-sub">This portal is private. Type the access key your admin gave you; this browser then stays
            unlocked for 30 days.</p>
          {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
          <div className="form-group">
            <label className="form-label" htmlFor="gate-key">Access key</label>
            <input id="gate-key" type="password" className="form-input" value={key} autoFocus autoComplete="off"
                   onChange={(e) => setKey(e.target.value)} required />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={busy || !key.trim()}>
            <KeyRound size={16} aria-hidden="true" /> {busy ? "Checking…" : "Unlock"}
          </button>
        </form>
      </section>
    </div>
  );
}
