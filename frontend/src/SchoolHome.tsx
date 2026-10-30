import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, ClipboardList, Database, GraduationCap, Link2, RefreshCw, School, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";

// The school's home: one card per area of work, each opening its area (HPC, UDISE+). The UDISE+ area's own page
// connects once (the person reads the captcha and types the OTP) and keeps a session for each of its four services.

interface UdiseService {
  key: string;
  name: string;
  what: string;
  icon: LucideIcon;
}

const UDISE_SERVICES: UdiseService[] = [
  { key: "dcf", name: "UDISE+ data capture", what: "The school's yearly data (DCF): enrolment, facilities, finance.", icon: Database },
  { key: "profile", name: "School Profile & Facilities", what: "Basic details, location, buildings and facilities of the school.", icon: School },
  { key: "teacher", name: "Teacher module", what: "Records of the school's teachers and staff.", icon: UserRound },
  { key: "sdms", name: "Student module (SDMS)", what: "Student records: profile, enrolment, promotion and transfer.", icon: GraduationCap },
];

interface UdiseStatus {
  connected: boolean;
  username: string;
  connected_at: string | null;
  services: { key: string; name: string; connected: boolean; why: string }[];
}
interface StepResult extends Partial<UdiseStatus> {
  success: boolean;
  status?: "captcha_required" | "otp_required" | "authenticated";
  captcha_image?: string;
  message?: string;
  error?: string;
}

export function SchoolHome({ api, onOpenHpc, onOpenUdise, teachers, students }: {
  api: Api; onOpenHpc: () => void; onOpenUdise: () => void; teachers: number; students: number;
}) {
  const [udise, setUdise] = useState<UdiseStatus | null>(null);
  useEffect(() => { call<UdiseStatus>(api, "GET", "/school/udise/status").then(setUdise).catch(() => setUdise(null)); }, [api]);
  const on = (udise?.services || []).filter((s) => s.connected).length;
  return (
    <div className="home-grid">
      <button type="button" className="home-card home-hpc" onClick={onOpenHpc}>
        <span className="home-icon" aria-hidden="true"><ClipboardList size={26} /></span>
        <span className="home-title">HPC</span>
        <span className="home-sub">Holistic Progress Card on PARAKH</span>
        <span className="home-desc">Teachers, their classes and every student's card: activities, answers, the Excel file and the sync to PARAKH.</span>
        <span className="home-stats">
          <span><b>{teachers}</b> teacher{teachers === 1 ? "" : "s"}</span>
          <span><b>{students}</b> student{students === 1 ? "" : "s"}</span>
        </span>
        <span className="home-open">Open HPC <ArrowRight size={16} aria-hidden="true" /></span>
      </button>
      <button type="button" className="home-card home-udise" onClick={onOpenUdise}>
        <span className="home-icon" aria-hidden="true"><Database size={26} /></span>
        <span className="home-title">UDISE+</span>
        <span className="home-sub">Unified District Information System for Education</span>
        <span className="home-desc">Students on SDMS: forms, new admissions, AADHAAR and APAAR, bulk shift, Dropbox and import, and reports.</span>
        <span className="home-stats">
          <span><b>{udise?.connected ? "Connected" : "Not connected"}</b></span>
          <span><b>{on}</b> of 4 services</span>
        </span>
        <span className="home-open">Open UDISE+ <ArrowRight size={16} aria-hidden="true" /></span>
      </button>
    </div>
  );
}

export function UdiseCard({ api, onOpenSdms }: { api: Api; onOpenSdms: () => void }) {
  const [status, setStatus] = useState<UdiseStatus | null>(null);
  const [step, setStep] = useState<"idle" | "login" | "captcha" | "otp">("idle");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [answer, setAnswer] = useState("");
  const [picture, setPicture] = useState("");
  const [note, setNote] = useState<{ kind: "error" | "info" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await call<UdiseStatus>(api, "GET", "/school/udise/status");
      setStatus(s);
      setUsername((u) => u || s.username);
    } catch {
      setStatus(null);
    }
  }, [api]);
  useEffect(() => { load(); }, [load]);

  const cancel = () => { setStep("idle"); setNote(null); setPicture(""); setAnswer(""); };
  const send = async (path: string, body?: unknown) => {
    setBusy(true);
    setNote(null);
    try {
      const r = await call<StepResult>(api, "POST", path, body);
      setAnswer("");
      if (r.status === "captcha_required") {
        setPicture(r.captcha_image || "");
        setStep("captcha");
        setNote(r.error ? { kind: "error", text: r.error } : null);
      } else if (r.status === "otp_required") {
        setStep("otp");
        setNote({ kind: "info", text: r.message || "Type the OTP." });
      } else if (r.status === "authenticated") {
        setStep("idle");
        setPassword("");
        setPicture("");
        const on = (r.services || []).filter((s) => s.connected).length;
        setNote({ kind: on ? "success" : "error", text: `Signed in to UDISE+. ${on} of 4 services connected.` });
        await load();
      } else if (!r.success) {
        setNote({ kind: "error", text: r.error || "UDISE+ did not accept the sign-in." });
        setPicture("");
        setStep("login");
      }
    } catch (e: any) {
      setNote({ kind: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const connectedKeys = new Set((status?.services || []).filter((s) => s.connected).map((s) => s.key));
  const why = Object.fromEntries((status?.services || []).map((s) => [s.key, s.why]));

  return (
    <section className="home-card home-udise" aria-labelledby="udise-title">
      <span className="home-icon" aria-hidden="true"><Database size={26} /></span>
      <h2 id="udise-title" className="home-title">UDISE+</h2>
      <span className="home-sub">Unified District Information System for Education</span>

      <div className="udise-conn">
        {status?.connected ? (
          <span className="udise-state on"><CheckCircle2 size={16} aria-hidden="true" /> Connected as <b>{status.username}</b></span>
        ) : (
          <span className="udise-state off">Not connected</span>
        )}
        {step === "idle" && (
          <span className="udise-conn-actions">
            <button type="button" className="btn btn-primary" onClick={() => { setNote(null); setStep("login"); }} disabled={busy}>
              <Link2 size={15} aria-hidden="true" /> {status?.connected ? "Connect again" : "Connect UDISE+"}
            </button>
            {status?.connected && (
              <button type="button" className="btn btn-outline" disabled={busy}
                      onClick={() => send("/school/udise/disconnect").then(load)}>Disconnect</button>
            )}
          </span>
        )}
      </div>

      {step === "login" && (
        <form className="udise-form" onSubmit={(e) => { e.preventDefault(); send("/school/udise/connect", { username, password }); }}>
          <label>UDISE+ username
            <input className="form-input" value={username} onChange={(e) => setUsername(e.target.value.replace(/[^a-zA-Z0-9._-]/g, ""))}
                   maxLength={20} autoComplete="username" required />
          </label>
          <label>Password
            <input className="form-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   maxLength={100} autoComplete="current-password"
                   placeholder={status?.username ? "Leave empty to use the saved one" : ""} required={!status?.username} />
          </label>
          <div className="udise-form-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || !username}>{busy ? "Opening UDISE+…" : "Next: captcha"}</button>
            <button type="button" className="btn btn-outline" onClick={cancel}>Cancel</button>
          </div>
        </form>
      )}

      {step === "captcha" && (
        <form className="udise-form" onSubmit={(e) => { e.preventDefault(); send("/school/udise/verify-captcha", { answer }); }}>
          <div className="udise-captcha">
            {picture && <img src={picture} alt="UDISE+ captcha: type the 6 characters it shows" />}
            <button type="button" className="btn btn-outline" onClick={() => send("/school/udise/new-captcha")} disabled={busy}
                    aria-label="Another captcha picture"><RefreshCw size={15} aria-hidden="true" /></button>
          </div>
          <label>Type the 6 characters in the picture
            <input className="form-input" value={answer} onChange={(e) => setAnswer(e.target.value.trim())} maxLength={6}
                   autoComplete="off" autoFocus required />
          </label>
          <div className="udise-form-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || answer.length !== 6}>{busy ? "Signing in…" : "Sign in"}</button>
            <button type="button" className="btn btn-outline" onClick={cancel}>Cancel</button>
          </div>
        </form>
      )}

      {step === "otp" && (
        <form className="udise-form" onSubmit={(e) => { e.preventDefault(); send("/school/udise/verify-otp", { otp: answer }); }}>
          <label>OTP sent to the registered mobile
            <input className="form-input" value={answer} onChange={(e) => setAnswer(e.target.value.replace(/\D/g, ""))}
                   inputMode="numeric" maxLength={8} autoComplete="one-time-code" autoFocus required />
          </label>
          <div className="udise-form-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || answer.length < 4}>{busy ? "Checking…" : "Verify OTP"}</button>
            <button type="button" className="btn btn-outline" onClick={cancel}>Cancel</button>
          </div>
        </form>
      )}

      {note && <p className={`udise-note ${note.kind}`} role={note.kind === "error" ? "alert" : "status"}>{note.text}</p>}

      <ul className="udise-list">
        {UDISE_SERVICES.map(({ key, name, what, icon: Icon }) => (
          <li key={key}>
            <Icon size={18} className="udise-icon" aria-hidden="true" />
            <span className="udise-text">
              <b>{name}</b>
              <small>{what}</small>
              {status && (connectedKeys.has(key)
                ? <span className="udise-badge on">Session saved</span>
                : <span className="udise-badge off">Not connected{why[key] ? ` - ${why[key]}` : ""}</span>)}
            </span>
            {key === "sdms" && connectedKeys.has(key) && (
              <button type="button" className="btn btn-primary udise-open" onClick={onOpenSdms}>View students</button>
            )}
          </li>
        ))}
      </ul>
      <p className="home-note">The captcha and OTP are always typed by you. The password and sessions are kept encrypted on this computer.</p>
    </section>
  );
}
