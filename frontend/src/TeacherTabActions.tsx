import { useState } from "react";
import { ExternalLink, KeyRound } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";

// For every teacher account of the school - from PARAKH's list or added by hand: open the teacher in a second tab
// (that tab has the teacher's session; this one stays the school), and save the teacher's own PARAKH login so the
// teacher tab connects with just the captcha.

export function TeacherTab({ api, teacherId, name, parakhLoginId, hasParakhLogin, onSaved, active = true }: {
  api: Api; teacherId: string; name: string; parakhLoginId?: string | null; hasParakhLogin?: boolean;
  onSaved?: () => void; active?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [id, setId] = useState(parakhLoginId || "");
  const [pw, setPw] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [saved, setSaved] = useState(!!hasParakhLogin);

  const openTab = async () => {
    setNote(null);
    const w = window.open("about:blank", "ta-teacher-tab");     // opened first, so it is not blocked as a pop-up
    try {
      const res = await call<{ tab: string; has_parakh_login: boolean }>(api, "POST", `/school/teachers/${teacherId}/open-tab`);
      const url = `/?tab=${encodeURIComponent(res.tab)}`;
      if (w) { w.location.href = url; w.focus(); } else window.open(url, "ta-teacher-tab");
      setNote(res.has_parakh_login ? "Opened in the teacher tab: press Connect there and type the captcha."
        : "Opened in the teacher tab. Save the teacher's PARAKH login here to connect there with one captcha.");
    } catch (e) {
      w?.close();
      setNote((e as Error).message);
    }
  };

  const save = async () => {
    setNote(null);
    try {
      await call(api, "PUT", `/school/teachers/${teacherId}/parakh-login`, { hpc_login_id: id.trim(), hpc_password: pw });
      setPw("");
      setSaved(true);
      setOpen(false);
      setNote("PARAKH login saved.");
      onSaved?.();
    } catch (e) {
      setNote((e as Error).message);
    }
  };

  const switchOn = async () => {
    setNote(null);
    try {
      await call(api, "PUT", `/school/teachers/${teacherId}`, { is_active: true });
      onSaved?.();
    } catch (e) {
      setNote((e as Error).message);
    }
  };

  if (!active) return (                      // a switched-off account cannot be opened: say so, offer to switch it on
    <div className="teacher-tab-actions">
      <span className="form-hint">Switched off - it cannot sign in or be opened.</span>
      <button type="button" className="btn btn-outline btn-sm" onClick={switchOn}>Switch on</button>
      {note && <div className="form-hint">{note}</div>}
    </div>
  );

  return (
    <div className="teacher-tab-actions">
      <button type="button" className="btn btn-primary btn-sm" onClick={openTab}
              title="Opens a second tab signed in as this teacher; this tab stays the school">
        <ExternalLink size={14} aria-hidden="true" /> Open as teacher
      </button>
      <button type="button" className="btn btn-outline btn-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <KeyRound size={14} aria-hidden="true" /> {saved ? "PARAKH login saved" : "PARAKH login"}
      </button>
      {open && (
        <div className="teacher-tab-login">
          <input type="text" className="form-input" aria-label={`PARAKH login ID of ${name}`} placeholder="PARAKH login ID"
                 value={id} onChange={(e) => setId(e.target.value)} />
          <input type="password" className="form-input" autoComplete="new-password" aria-label={`PARAKH password of ${name}`}
                 placeholder={saved ? "Saved - type to change" : "Teacher's PARAKH password"} value={pw}
                 onChange={(e) => setPw(e.target.value)} />
          <button type="button" className="btn btn-outline btn-sm" disabled={!id.trim() || pw.length < 3} onClick={save}>Save</button>
        </div>)}
      {note && <div className="form-hint">{note}</div>}
    </div>
  );
}
