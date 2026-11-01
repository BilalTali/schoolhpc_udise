import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { call } from "./api";
import type { Api } from "./api";

// Teachers come from PARAKH (the school's PARAKH login, read only): their login ID here IS their PARAKH ID; the school
// sets only the password for this app. Their own PARAKH password is never asked for here - they type it when they
// connect to PARAKH to save cards.

interface Klass { stage: string; grade: string; section: string; class_teacher: boolean }
interface Row { parakh_id: string; name: string; teacher_code: string; registered: boolean; classes: Klass[];
  account: { id: string; username: string; is_active: boolean; login_matches: boolean } | null }
interface Result { parakh_id: string; status: "created" | "updated" | "error"; message: string }

export function ParakhTeachers({ api, onChanged }: { api: Api; onChanged: () => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [shared, setShared] = useState("");
  const [results, setResults] = useState<Record<string, Result>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await call<{ teachers: Row[] }>(api, "GET", "/school/teachers/parakh")).teachers);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [api]);
  useEffect(() => { void load(); }, [load]);

  const send = async (items: { parakh_id: string; password?: string }[]) => {
    if (!items.length) return;
    setSaving(true);
    setError(null);
    try {
      const r = await call<{ results: Result[] }>(api, "POST", "/school/teachers/parakh/import", { teachers: items });
      setResults((prev) => ({ ...prev, ...Object.fromEntries(r.results.map((x) => [x.parakh_id, x])) }));
      setPasswords({});
      await load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const missing = (rows || []).filter((r) => !r.account);
  return (
    <div className="ui-panel">
      <div className="panel-header">
        <div className="panel-title"><span>Teachers on PARAKH</span></div>
        <button type="button" className="btn btn-outline" onClick={load} disabled={loading || saving}>
          <RefreshCw size={15} className={loading ? "spin" : ""} aria-hidden="true" /> Read again from PARAKH
        </button>
      </div>
      <p className="form-hint">The school's teachers as PARAKH has them, with the classes PARAKH makes them class teacher
        of. A teacher signs in here with their <b>PARAKH ID</b> and the password you set; they type their own PARAKH
        password only when they connect to PARAKH to save cards.</p>
      {error && <div className="alert-box alert-error" role="alert"><AlertCircle size={18} aria-hidden="true" /><div>{error}</div></div>}
      {rows && missing.length > 1 && (
        <div className="bulk-fill">
          <span className="form-label">One password for all {missing.length} new teachers</span>
          <input type="password" className="form-input" value={shared} onChange={(e) => setShared(e.target.value)}
                 placeholder="8 or more characters" autoComplete="new-password" aria-label="Password for all new teachers" />
          <button type="button" className="btn btn-primary" disabled={saving || shared.length < 8}
                  onClick={() => send(missing.map((r) => ({ parakh_id: r.parakh_id, password: shared })))}>
            Create {missing.length} logins
          </button>
        </div>
      )}
      {rows && (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead><tr><th>Teacher (PARAKH)</th><th>Login ID = PARAKH ID</th><th>Class teacher of</th><th>Login here</th><th>Password for this app</th></tr></thead>
            <tbody>{rows.map((r) => {
              const res = results[r.parakh_id];
              const pw = passwords[r.parakh_id] || "";
              return (
                <tr key={r.parakh_id}>
                  <td><b>{r.name}</b>{r.teacher_code && <div className="form-hint">Code: {r.teacher_code}</div>}
                    {!r.registered && <div className="form-hint">Registration not finished on PARAKH</div>}</td>
                  <td><code>{r.parakh_id}</code></td>
                  <td>{r.classes.filter((c) => c.class_teacher).map((c) => `${c.grade} ${c.section}`).join(", ") || <span className="form-hint">None on PARAKH</span>}
                    {r.classes.some((c) => !c.class_teacher) && <div className="form-hint">Also teaches: {r.classes.filter((c) => !c.class_teacher).map((c) => `${c.grade} ${c.section}`).join(", ")}</div>}</td>
                  <td>{r.account
                    ? <span className="status-pill active">{r.account.is_active ? "Has a login" : "Switched off"}{!r.account.login_matches && ` (login: ${r.account.username})`}</span>
                    : <span className="status-pill inactive">No login yet</span>}
                    {res && <div className={res.status === "error" ? "field-problem" : "form-hint"}>
                      {res.status !== "error" && <CheckCircle2 size={12} aria-hidden="true" />} {res.message}</div>}</td>
                  <td>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <input type="password" className="form-input" value={pw} autoComplete="new-password"
                             placeholder={r.account ? "New password (optional)" : "8 or more characters"}
                             aria-label={`Password for ${r.name}`}
                             onChange={(e) => setPasswords((p) => ({ ...p, [r.parakh_id]: e.target.value }))} />
                      <button type="button" className="btn btn-outline" disabled={saving || (!r.account && pw.length < 8) || (!!pw && pw.length < 8)}
                              onClick={() => send([{ parakh_id: r.parakh_id, ...(pw ? { password: pw } : {}) }])}>
                        {r.account ? (pw ? "Set password" : "Update from PARAKH") : "Create login"}
                      </button>
                    </div>
                  </td>
                </tr>);
            })}
            {!rows.length && <tr><td colSpan={5} className="lib-muted">PARAKH lists no teachers for this school.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
