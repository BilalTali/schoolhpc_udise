import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, IdCard, RefreshCw } from "lucide-react";
import { ApiError, call } from "./api";
import type { Api } from "./api";
import { ApaarSheet } from "./ApaarSheet";
import { CardHub } from "./CardHub";
import { downloadSheet } from "./downloadSheet";

// AADHAAR verification and APAAR IDs, the way SDMS's own AADHAAR MBU and APAAR modules work: verify again (UIDAI's
// error), correct the details to match the card then verify (a mismatch), generate APAAR IDs (a PEN and a verified
// AADHAAR). Every step needs the person to confirm the parent's consent, as SDMS asks.

type Group = "verified" | "retry" | "mismatch" | "no_aadhaar";
interface Row {
  student_id: number; name: string; class: string; section: string; pen: string; gender: number; dob: string;
  name_as_aadhaar: string; aadhaar: string; group: Group; status: string; reason: string; checked_on: string;
  mbu: string | null; apaar_id: string | null; apaar_status: string | null; apaar_ready: boolean; apaar_blocked: string | null;
}
interface Counts { verified: number; retry: number; mismatch: number; no_aadhaar: number; apaar_ready: number; apaar_done: number; apaar_waiting: number }
interface Result { student_id: number; verified: boolean; status: string | null; reason: string | null; error: string | null }
interface Job { status: "RUNNING" | "COMPLETED" | "FAILED"; done: number; total: number; results: Result[]; error: string | null }
interface View { fetched_at: string; counts: Counts; students: Row[]; apaar_read: boolean; job: Job | null }

const GENDER: Record<number, string> = { 1: "Male", 2: "Female", 3: "Transgender" };
const Alert = ({ text }: { text: string }) => (
  <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{text}</div></div>
);

export function AadhaarPage({ api }: { api: Api }) {
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [consent, setConsent] = useState(false);
  const [fixing, setFixing] = useState<number | null>(null);
  const [apaarFor, setApaarFor] = useState<number | null>(null);
  const [done, setDone] = useState<Record<number, string>>({});         // student -> what just happened

  const load = useCallback(async () => {
    try {
      const v = await call<View>(api, "GET", "/school/udise/sdms/aadhaar");
      setView(v);
      setPicked((p) => (p.size ? p : new Set(v.students.filter((s) => s.group === "retry").map((s) => s.student_id))));
      return v;
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "Fetch the students on the Students (SDMS) page first." : (e as Error).message);
      return null;
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  const running = view?.job?.status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => { void load(); }, 2000);
    return () => window.clearTimeout(t);
  }, [running, view, load]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!view) return <div className="ui-panel">{error ? <Alert text={error} /> : <p className="lib-muted">Loading…</p>}</div>;
  const by = (g: Group) => view.students.filter((s) => s.group === g);
  const retry = by("retry");
  const mismatch = by("mismatch");
  const ready = view.students.filter((s) => s.apaar_ready);
  const c = view.counts;

  const verifyPanel = (
      <div className="ui-panel">
        <p className="lib-muted">UIDAI answered "Technical/Auth Server Error - Please Try After Some Time" for these students: their details are
          fine, the check just did not go through. Asking UIDAI again usually verifies them.</p>
        {retry.length > 0 && (
          <>
            <ul className="aad-list">
              {retry.map((s) => (
                <li key={s.student_id}>
                  <label><input type="checkbox" checked={picked.has(s.student_id)} disabled={running}
                                onChange={(e) => setPicked((p) => { const n = new Set(p); if (e.target.checked) n.add(s.student_id); else n.delete(s.student_id); return n; })} />
                    {" "}<b>{s.name}</b> · {s.class} {s.section} · checked {s.checked_on || "—"}</label>
                </li>
              ))}
            </ul>
            <label className="aad-consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              {" "}The parents of the ticked students have given consent to use their AADHAAR for demographic authentication.</label>
            <button type="button" className="btn btn-primary" disabled={busy || running || !consent || !picked.size}
                    onClick={() => run(() => call(api, "POST", "/school/udise/sdms/aadhaar/verify", { student_ids: [...picked], consent: true }))}>
              <RefreshCw size={15} aria-hidden="true" className={running ? "spin" : ""} /> Verify {picked.size} with UIDAI
            </button>
          </>
        )}
        {view.job && (
          <div className="sdms-progress" role="status">
            {running && <div><b>Asking UIDAI…</b> {view.job.done} of {view.job.total}</div>}
            {view.job.status === "FAILED" && view.job.error && <Alert text={view.job.error} />}
            {view.job.results.length > 0 && (
              <ul className="aad-results">
                {view.job.results.map((r) => {
                  const s = view.students.find((x) => x.student_id === r.student_id);
                  return <li key={r.student_id} className={r.verified ? "ok" : "bad"}>
                    {r.verified ? <CheckCircle2 size={14} aria-hidden="true" /> : <AlertCircle size={14} aria-hidden="true" />}
                    {" "}<b>{s?.name || r.student_id}</b>: {r.error || (r.verified ? "Verified" : `${r.status || ""} - ${r.reason || ""}`)}</li>;
                })}
              </ul>
            )}
          </div>
        )}
      </div>
  );
  const mismatchPanel = (
      <div className="ui-panel">
        <p className="lib-muted">UIDAI says the name, gender or date of birth is not the same as on the AADHAAR. Look at the student's AADHAAR card and
          enter the details exactly as printed on it (the AADHAAR number again, too); they are saved on SDMS and checked with UIDAI at once.</p>
        <ul className="aad-list">
          {mismatch.map((s) => (
            <li key={s.student_id}>
              <div className="aad-row">
                <span><b>{s.name}</b> · {s.class} {s.section} · on SDMS: name as AADHAAR "{s.name_as_aadhaar}", {GENDER[s.gender] || "?"}, born {s.dob}</span>
                {done[s.student_id] ? <span className="aad-done">{done[s.student_id]}</span>
                  : <button type="button" className="btn btn-outline btn-sm" onClick={() => setFixing(fixing === s.student_id ? null : s.student_id)}>Correct</button>}
              </div>
              {fixing === s.student_id && (
                <CorrectForm row={s} busy={busy} onSave={(body) => run(async () => {
                  const r = await call<{ verified: boolean; status: string; reason: string }>(api, "POST", `/school/udise/sdms/aadhaar/${s.student_id}/correct`, body);
                  setDone((d) => ({ ...d, [s.student_id]: r.verified ? "Saved and verified" : `Saved; UIDAI: ${r.reason || r.status}` }));
                  setFixing(null);
                })} />
              )}
            </li>
          ))}
          {mismatch.length === 0 && <li className="lib-muted">None.</li>}
        </ul>
      </div>
  );
  const apaarPanel = (
      <div className="ui-panel">
        <div className="sdms-head">
          <span />
          <button type="button" className="btn btn-outline" disabled={busy}
                  onClick={() => run(() => call(api, "POST", "/school/udise/sdms/apaar/read"))}>
            <RefreshCw size={15} aria-hidden="true" className={busy ? "spin" : ""} /> Read APAAR status from SDMS
          </button>
        </div>
        <p className="lib-muted">SDMS generates an APAAR ID only for a student with a PEN and a verified AADHAAR, and only with the father's, mother's or
          legal guardian's physical consent (relation, name, ID proof, place and date). {!view.apaar_read && "Read the APAAR status first, so students who already have one are left out."}</p>
        <h4 className="aad-sub">For many students: the consent sheet</h4>
        <ApaarSheet api={api} ready={view.apaar_read ? c.apaar_ready : 0} onDone={() => { void load(); }} />
        <h4 className="aad-sub">Or one student at a time</h4>
        <ul className="aad-list">
          {ready.map((s) => (
            <li key={s.student_id}>
              <div className="aad-row">
                <span><b>{s.name}</b> · {s.class} {s.section} · PEN {s.pen}{s.mbu ? ` · ${s.mbu}` : ""}
                  {s.apaar_status && <small className="aad-note">Last time on SDMS: {s.apaar_status}</small>}</span>
                {done[s.student_id] ? <span className="aad-done">{done[s.student_id]}</span>
                  : <button type="button" className="btn btn-outline btn-sm" onClick={() => setApaarFor(apaarFor === s.student_id ? null : s.student_id)}>Generate APAAR</button>}
              </div>
              {apaarFor === s.student_id && (
                <ApaarForm busy={busy} onSave={(body) => run(async () => {
                  const r = await call<{ apaar_id: string }>(api, "POST", `/school/udise/sdms/apaar/${s.student_id}`, body);
                  setDone((d) => ({ ...d, [s.student_id]: `APAAR ID ${r.apaar_id}` }));
                  setApaarFor(null);
                })} />
              )}
            </li>
          ))}
          {ready.length === 0 && <li className="lib-muted">No student is ready for an APAAR ID right now.</li>}
          {view.apaar_read && c.apaar_waiting > 0 && (
            <li className="lib-muted">{c.apaar_waiting} more student{c.apaar_waiting === 1 ? "" : "s"} without an APAAR ID wait for their AADHAAR
              to be verified (steps 1 and 2 above).</li>
          )}
        </ul>
      </div>
  );

  return (
    <div className="sdms">
      {error && <Alert text={error} />}
      <CardHub label="AADHAAR & APAAR" cards={[
        { key: "retry", title: "Verify again", icon: RefreshCw, stat: c.retry, statLabel: "students", tone: c.retry ? "warn" : "good",
          about: "UIDAI had a technical error: the details are fine, ask UIDAI again (with the parents' consent).", body: () => verifyPanel },
        { key: "mismatch", title: "Details do not match", icon: AlertCircle, stat: c.mismatch, statLabel: "students", tone: c.mismatch ? "bad" : "good",
          about: "Name, gender or date of birth differs from the AADHAAR card: enter them as on the card, then verify.", body: () => mismatchPanel },
        { key: "apaar", title: "APAAR ID", icon: IdCard, stat: view.apaar_read ? c.apaar_done : "?", statLabel: view.apaar_read ? `generated · ${c.apaar_ready} ready` : "read the status first",
          tone: view.apaar_read && c.apaar_ready ? "warn" : "info",
          about: "Generate APAAR IDs one by one or from the parents' consent sheet; read SDMS's status and reasons.", body: () => apaarPanel },
        { key: "verified", title: "AADHAAR verified", icon: CheckCircle2, stat: c.verified, statLabel: `of ${view.students.length}`, tone: "good",
          about: `${c.no_aadhaar} without an AADHAAR on SDMS. Download the APAAR status (completed / pending with reasons) as Excel.`,
          disabled: view.apaar_read ? undefined : "Read the APAAR status from SDMS first (APAAR ID card)",
          onOpen: async () => setError(await downloadSheet(api, "/school/udise/sdms/apaar/status.xlsx", "APAAR_status.xlsx")) },
      ]} />
    </div>
  );
}

function CorrectForm({ row, busy, onSave }: { row: Row; busy: boolean; onSave: (body: unknown) => void }) {
  const [aadhaar, setAadhaar] = useState("");
  const [name, setName] = useState(row.name_as_aadhaar || row.name);
  const [gender, setGender] = useState<number>(row.gender);
  const [dob, setDob] = useState(row.dob || "");
  const [ok, setOk] = useState(false);
  const digits = aadhaar.replace(/\s/g, "");
  return (
    <form className="udise-form" onSubmit={(e) => {
      e.preventDefault();
      onSave({ aadhaar: digits, name_as_aadhaar: name, gender: gender !== row.gender ? gender : null, dob: dob !== row.dob ? dob : null, consent: true });
    }}>
      <label>AADHAAR number (12 digits, from the card)
        <input className="form-input" value={aadhaar} inputMode="numeric" maxLength={14} autoComplete="off"
               onChange={(e) => setAadhaar(e.target.value.replace(/[^\d ]/g, ""))} required />
      </label>
      <label>Name exactly as on the AADHAAR card
        <input className="form-input" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>Gender (as on the card)
        <select className="form-input" value={gender} onChange={(e) => setGender(Number(e.target.value))}>
          {Object.entries(GENDER).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>Date of birth (DD/MM/YYYY, as on the card)
        <input className="form-input" value={dob} maxLength={10} onChange={(e) => setDob(e.target.value)} required />
      </label>
      <label className="aad-consent"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        {" "}The parent has given consent to use the AADHAAR for demographic authentication.</label>
      <div className="udise-form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy || !ok || digits.length !== 12}>Save on SDMS and verify</button>
      </div>
    </form>
  );
}

function ApaarForm({ busy, onSave }: { busy: boolean; onSave: (body: unknown) => void }) {
  const [f, setF] = useState({ relation: 1, name: "", id_type: 1, id_no: "", place: "", date: "" });
  const [ok, setOk] = useState(false);
  const set = (k: string, v: string | number) => setF((x) => ({ ...x, [k]: v }));
  return (
    <form className="udise-form" onSubmit={(e) => { e.preventDefault(); onSave({ ...f, consent: true }); }}>
      <label>Consent given by
        <select className="form-input" value={f.relation} onChange={(e) => set("relation", Number(e.target.value))}>
          <option value={1}>Father</option><option value={2}>Mother</option><option value={3}>Legal Guardian</option>
        </select>
      </label>
      <label>Their name<input className="form-input" value={f.name} maxLength={100} onChange={(e) => set("name", e.target.value)} required /></label>
      <label>Their ID proof
        <select className="form-input" value={f.id_type} onChange={(e) => set("id_type", Number(e.target.value))}>
          <option value={1}>AADHAAR</option><option value={2}>PAN</option><option value={3}>EPIC/Voter ID</option>
          <option value={4}>Driving License</option><option value={5}>Passport</option>
        </select>
      </label>
      <label>ID proof number<input className="form-input" value={f.id_no} maxLength={30} autoComplete="off" onChange={(e) => set("id_no", e.target.value)} required /></label>
      <label>Place of the physical consent<input className="form-input" value={f.place} maxLength={60} onChange={(e) => set("place", e.target.value)} required /></label>
      <label>Date of the physical consent<input className="form-input" type="date" value={f.date} onChange={(e) => set("date", e.target.value)} required /></label>
      <label className="aad-consent"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        {" "}The parent/guardian named above signed the physical consent for the APAAR ID and DigiLocker on this date.</label>
      <div className="udise-form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy || !ok}>Generate APAAR ID on SDMS</button>
      </div>
    </form>
  );
}
