import { useEffect, useId, useRef, useState } from "react";
import { AlertCircle, KeyRound, RefreshCw } from "lucide-react";
import { apiFetch } from "./api";

// PARAKH's login captcha, answered by the person (the app never reads it by itself unless the
// unsupported automatic mode is switched on). The picture comes from PARAKH through our server.

export interface CaptchaResult {
  status: "authenticated" | "otp_required";
  user?: string;
  message?: string;
}

export function CaptchaStep({ who, image, onDone, onCancel }: {
  who: "teacher" | "school";
  image: string;
  onDone: (result: CaptchaResult) => void;
  onCancel: () => void;
}) {
  const [picture, setPicture] = useState(image);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();

  useEffect(() => { setPicture(image); }, [image]);
  useEffect(() => { input.current?.focus(); }, [picture]);

  const post = async (path: string, body?: unknown) => {
    const res = await apiFetch(`/${who}/hpc/${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) { setError("Type the answer shown in the picture."); return; }
    setBusy(true);
    setError(null);
    try {
      const { ok, data } = await post("verify-captcha", { answer: answer.trim() });
      if (data.status === "captcha_required") {
        if (data.captcha_image) setPicture(data.captcha_image);
        setAnswer("");
        setError(data.error || "Please try again.");
      } else if (ok && (data.status === "authenticated" || data.status === "otp_required")) {
        onDone(data);
      } else {
        setError(data.detail || data.error || "Login failed.");
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const another = async () => {
    setBusy(true);
    setError(null);
    try {
      const { ok, data } = await post("new-captcha");
      if (ok && data.captcha_image) { setPicture(data.captcha_image); setAnswer(""); }
      else setError(data.detail || "Please click Connect again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="captcha-step" onSubmit={submit} aria-labelledby={`${id}-title`}>
      <div id={`${id}-title`} className="captcha-title"><KeyRound size={16} aria-hidden="true" /> Type the answer shown in the picture to connect to PARAKH</div>
      <div className="captcha-row">
        <img src={picture} alt="PARAKH login captcha: a small sum to work out" className="captcha-img" />
        <button type="button" className="btn btn-outline" onClick={another} disabled={busy}>
          <RefreshCw size={14} aria-hidden="true" /> New picture
        </button>
      </div>
      <div className="captcha-row">
        <label htmlFor={`${id}-answer`} className="form-label">Answer</label>
        <input id={`${id}-answer`} ref={input} className="form-input captcha-input" inputMode="numeric" autoComplete="off"
               value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={20} />
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
        <button type="button" className="portal-link-btn" onClick={onCancel}>Cancel</button>
      </div>
      <div aria-live="polite">
        {error && <div className="alert-box alert-error lib-inline-alert" role="alert"><AlertCircle size={16} aria-hidden="true" /><div>{error}</div></div>}
      </div>
      <p className="lib-muted">You only need to do this when you connect. The app keeps your PARAKH session going after that.</p>
    </form>
  );
}
