import { useCallback, useEffect, useState } from "react";
import { AlertCircle, BookOpen, Building2, CheckCircle2, ClipboardList, KeyRound, LayoutDashboard, LogOut, Plus, Power } from "lucide-react";
import { call } from "../api";
import type { Api } from "../api";
import { ActivityEditor } from "./ActivityEditor";
import { Modal } from "./Dialog";
import { STAGES, formatWhen } from "./types";
import type { Subject } from "./types";

// The admin: one account above every school - schools and teachers, a platform dashboard, the
// activities offered to every school, and the audit trail. No students' records and no PARAKH passwords here.

interface Stats {
  schools: number; schools_active: number; teachers: number; teachers_active: number; uploads: number;
  cards_saved: number; cards_failed: number; last_upload_at: string | null; activities_waiting: number; activities_offered: number;
}
interface SchoolRow {
  id: string; udise_code: string; school_name: string; district: string; state: string; admin_email: string; is_active: boolean;
  teachers: number; teachers_active: number; cards_saved: number; cards_failed: number; last_upload_at: string | null;
}
interface TeacherRow {
  id: string; teacher_name: string; username: string; stages: string[]; is_active: boolean; last_login: string | null;
  cards_saved: number; cards_failed: number;
}
interface ActivityRow { id: string; title: string; stage: string; grade: string; subjects: string[]; made_by: string; state: string }
interface AuditRow { at: string; actor: string; school: string; action: string; entity: string; entity_id: string | null }

type Tab = "overview" | "schools" | "activities" | "audit";
const TABS: { key: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "schools", label: "Schools & teachers", icon: Building2 },
  { key: "activities", label: "Activities for every school", icon: BookOpen },
  { key: "audit", label: "Audit trail", icon: ClipboardList },
];

export function PlatformAdmin({ api, onLogout }: { api: Api; onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const say = (text: string, type: "success" | "error" = "success") => setMessage({ type, text });
  return (
    <div className="pa-shell">
      <header className="pa-head">
        <div>
          <h1>Teacher Assist · Admin</h1>
          <p className="lib-muted">Every school and teacher on this app. Students' records and PARAKH passwords are never shown here.</p>
        </div>
        <button type="button" className="btn btn-outline" onClick={onLogout}><LogOut size={15} aria-hidden="true" /> Sign out</button>
      </header>
      <nav className="pa-tabs" role="tablist" aria-label="Admin">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""}
                  onClick={() => { setTab(key); setMessage(null); }}>
            <Icon size={15} aria-hidden="true" /> {label}
          </button>
        ))}
      </nav>
      {message && (
        <div className={`alert-box ${message.type === "error" ? "alert-error" : "alert-success"}`} role={message.type === "error" ? "alert" : "status"}>
          {message.type === "error" ? <AlertCircle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
          <div>{message.text}</div>
        </div>
      )}
      {tab === "overview" && <Overview api={api} onError={(t) => say(t, "error")} />}
      {tab === "schools" && <Schools api={api} say={say} />}
      {tab === "activities" && <Activities api={api} say={say} />}
      {tab === "audit" && <Audit api={api} onError={(t) => say(t, "error")} />}
    </div>
  );
}

function Overview({ api, onError }: { api: Api; onError: (t: string) => void }) {
  const [s, setS] = useState<Stats | null>(null);
  useEffect(() => { call<Stats>(api, "GET", "/platform/stats").then(setS).catch((e) => onError(e.message)); }, [api]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return <p className="lib-muted">Loading…</p>;
  const tiles: [string, string | number, string][] = [
    ["Schools", s.schools, `${s.schools_active} switched on`],
    ["Teachers", s.teachers, `${s.teachers_active} switched on`],
    ["Cards saved to PARAKH", s.cards_saved, `${s.cards_failed} not saved`],
    ["Uploads", s.uploads, s.last_upload_at ? `last ${formatWhen(s.last_upload_at)}` : "none yet"],
    ["Activities offered to every school", s.activities_offered, `${s.activities_waiting} waiting for review`],
  ];
  return (
    <section className="pa-tiles" aria-label="Totals across every school">
      {tiles.map(([label, value, note]) => (
        <div key={label} className="pa-tile"><span className="lib-muted">{label}</span><b>{value}</b><small className="lib-muted">{note}</small></div>
      ))}
    </section>
  );
}

function Schools({ api, say }: { api: Api; say: (t: string, type?: "success" | "error") => void }) {
  const [rows, setRows] = useState<SchoolRow[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [teachers, setTeachers] = useState<Record<string, TeacherRow[]>>({});
  const [password, setPassword] = useState<{ kind: "schools" | "teachers"; id: string; name: string } | null>(null);
  const load = useCallback(() => {
    call<SchoolRow[]>(api, "GET", "/platform/schools").then(setRows).catch((e) => say(e.message, "error"));
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const loadTeachers = (id: string) =>
    call<TeacherRow[]>(api, "GET", `/platform/schools/${id}/teachers`).then((t) => setTeachers((x) => ({ ...x, [id]: t })))
      .catch((e) => say(e.message, "error"));
  const toggle = async (kind: "schools" | "teachers", id: string, on: boolean, name: string, schoolId?: string) => {
    if (!on && !window.confirm(kind === "schools"
      ? `Switch off ${name}? Its admin and every teacher are signed out and cannot sign in until it is switched on again.`
      : `Switch off ${name}? They are signed out and cannot sign in until switched on again.`)) return;
    try {
      await call(api, "PUT", `/platform/${kind}/${id}`, { is_active: on });
      say(`${name} is switched ${on ? "on" : "off"}.`);
      load();
      if (schoolId) loadTeachers(schoolId);
    } catch (e: any) { say(e.message, "error"); }
  };
  if (!rows) return <p className="lib-muted">Loading…</p>;
  return (
    <section className="ui-panel">
      <table className="data-table">
        <caption className="sr-only">Every school</caption>
        <thead><tr><th scope="col">School</th><th scope="col">UDISE · admin email</th><th scope="col">Teachers</th>
          <th scope="col">Cards saved</th><th scope="col">Last upload</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <SchoolLine key={s.id} s={s} open={open === s.id} teachers={teachers[s.id]}
                        onOpen={() => { setOpen(open === s.id ? null : s.id); if (open !== s.id) loadTeachers(s.id); }}
                        onToggle={() => toggle("schools", s.id, !s.is_active, s.school_name)}
                        onPassword={() => setPassword({ kind: "schools", id: s.id, name: s.school_name })}
                        onTeacherToggle={(t) => toggle("teachers", t.id, !t.is_active, t.teacher_name, s.id)}
                        onTeacherPassword={(t) => setPassword({ kind: "teachers", id: t.id, name: t.teacher_name })} />
          ))}
          {rows.length === 0 && <tr><td colSpan={7} className="lib-muted">No school has registered yet.</td></tr>}
        </tbody>
      </table>
      {password && <PasswordDialog api={api} target={password} onClose={() => setPassword(null)}
                                    onDone={(t) => { setPassword(null); say(t); }} />}
    </section>
  );
}

function SchoolLine({ s, open, teachers, onOpen, onToggle, onPassword, onTeacherToggle, onTeacherPassword }: {
  s: SchoolRow; open: boolean; teachers?: TeacherRow[]; onOpen: () => void; onToggle: () => void; onPassword: () => void;
  onTeacherToggle: (t: TeacherRow) => void; onTeacherPassword: (t: TeacherRow) => void;
}) {
  return (
    <>
      <tr>
        <th scope="row"><b>{s.school_name}</b><br /><small className="lib-muted">{[s.district, s.state].filter(Boolean).join(", ")}</small></th>
        <td>{s.udise_code}<br /><small className="lib-muted">{s.admin_email}</small></td>
        <td>{s.teachers_active} of {s.teachers}</td>
        <td>{s.cards_saved}{s.cards_failed ? <small className="lib-muted"> · {s.cards_failed} not saved</small> : null}</td>
        <td>{s.last_upload_at ? formatWhen(s.last_upload_at) : "—"}</td>
        <td><span className={`lib-badge ${s.is_active ? "lib-badge-ok" : "lib-badge-warn"}`}>{s.is_active ? "On" : "Off"}</span></td>
        <td className="pa-actions">
          <button type="button" className="portal-link-btn" aria-expanded={open} onClick={onOpen}>{open ? "Hide teachers" : "Teachers"}</button>
          <button type="button" className="portal-link-btn" onClick={onPassword}><KeyRound size={13} aria-hidden="true" /> New password</button>
          <button type="button" className="portal-link-btn" onClick={onToggle}><Power size={13} aria-hidden="true" /> {s.is_active ? "Switch off" : "Switch on"}</button>
        </td>
      </tr>
      {open && (
        <tr className="pa-sub"><td colSpan={7}>
          {!teachers ? <span className="lib-muted">Loading…</span> : teachers.length === 0 ? <span className="lib-muted">No teachers yet.</span> : (
            <table className="data-table">
              <caption className="sr-only">Teachers of {s.school_name}</caption>
              <thead><tr><th scope="col">Teacher</th><th scope="col">Stages</th><th scope="col">Last sign-in</th>
                <th scope="col">Cards saved</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
              <tbody>
                {teachers.map((t) => (
                  <tr key={t.id}>
                    <th scope="row">{t.teacher_name}<br /><small className="lib-muted">{t.username}</small></th>
                    <td>{t.stages.join(", ")}</td>
                    <td>{t.last_login ? formatWhen(t.last_login) : "never"}</td>
                    <td>{t.cards_saved}{t.cards_failed ? <small className="lib-muted"> · {t.cards_failed} not saved</small> : null}</td>
                    <td><span className={`lib-badge ${t.is_active ? "lib-badge-ok" : "lib-badge-warn"}`}>{t.is_active ? "On" : "Off"}</span></td>
                    <td className="pa-actions">
                      <button type="button" className="portal-link-btn" onClick={() => onTeacherPassword(t)}><KeyRound size={13} aria-hidden="true" /> New password</button>
                      <button type="button" className="portal-link-btn" onClick={() => onTeacherToggle(t)}><Power size={13} aria-hidden="true" /> {t.is_active ? "Switch off" : "Switch on"}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </td></tr>
      )}
    </>
  );
}

function PasswordDialog({ api, target, onClose, onDone }: {
  api: Api; target: { kind: "schools" | "teachers"; id: string; name: string }; onClose: () => void; onDone: (t: string) => void;
}) {
  const [pw, setPw] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ok = pw.length >= 8 && pw === again;
  const save = async () => {
    try {
      await call(api, "POST", `/platform/${target.kind}/${target.id}/password`, { password: pw });
      onDone(`New password set for ${target.name}. Their old sessions have ended; give them the new password in person.`);
    } catch (e: any) { setError(e.message); }
  };
  return (
    <Modal title={`New password for ${target.name}`} onClose={onClose}
           subtitle={<span className="lib-muted">At least 8 characters. It is not shown anywhere again.</span>}
           footer={<><button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
             <button type="button" className="btn btn-primary" onClick={save} disabled={!ok}>Set password</button></>}>
      <div className="form-group"><label className="form-label" htmlFor="pa-pw">New password</label>
        <input id="pa-pw" type="password" className="form-input" value={pw} minLength={8} autoComplete="new-password" onChange={(e) => setPw(e.target.value)} /></div>
      <div className="form-group"><label className="form-label" htmlFor="pa-pw2">Type it again</label>
        <input id="pa-pw2" type="password" className="form-input" value={again} autoComplete="new-password" onChange={(e) => setAgain(e.target.value)} /></div>
      {again && pw !== again && <p className="field-problem">The two passwords are not the same.</p>}
      {error && <p className="field-problem" role="alert">{error}</p>}
    </Modal>
  );
}

function Activities({ api, say }: { api: Api; say: (t: string, type?: "success" | "error") => void }) {
  const [rows, setRows] = useState<ActivityRow[] | null>(null);
  const [adding, setAdding] = useState<{ stage: string; subjects: Subject[]; consent: string } | null>(null);
  const load = useCallback(() => {
    call<ActivityRow[]>(api, "GET", "/platform/activities").then(setRows).catch((e) => say(e.message, "error"));
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const start = async (stage: string) => {
    try {
      const l = await call<{ subjects: Subject[]; consent_text: string }>(api, "GET", `/activity-library?stage=${stage}&page_size=1`);
      setAdding({ stage, subjects: l.subjects, consent: l.consent_text });
    } catch (e: any) { say(e.message, "error"); }
  };
  const act = async (id: string, what: "offer" | "withdraw", title: string) => {
    try {
      await call(api, "POST", `/platform/activities/${id}/${what}`);
      say(what === "offer" ? `"${title}" is now offered to every school.` : `"${title}" is no longer offered to other schools.`);
      load();
    } catch (e: any) { say(e.message, "error"); }
  };
  return (
    <section className="ui-panel">
      <div className="tp-row">
        <span className="lib-muted">Add an activity for every school:</span>
        {STAGES.map((s) => (
          <button key={s.id} type="button" className="btn btn-outline btn-sm" onClick={() => start(s.id)}><Plus size={13} aria-hidden="true" /> {s.id}</button>
        ))}
      </div>
      <p className="lib-muted">Activities you add stay hidden until you press <b>Offer to every school</b>. Activities teachers share "with other schools" wait here for your review.</p>
      {!rows ? <p className="lib-muted">Loading…</p> : (
        <table className="data-table">
          <caption className="sr-only">Activities offered, or waiting to be offered, to every school</caption>
          <thead><tr><th scope="col">Activity</th><th scope="col">Stage · grade</th><th scope="col">Subject</th><th scope="col">Made by</th>
            <th scope="col">State</th><th scope="col">Actions</th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id}>
                <th scope="row">{a.title}</th>
                <td>{a.stage}{a.grade ? ` · ${a.grade}` : ""}</td>
                <td>{a.subjects.join(", ") || "—"}</td>
                <td>{a.made_by}</td>
                <td><span className={`lib-badge ${a.state === "offered" ? "lib-badge-ok" : a.state === "waiting" ? "lib-badge-warn" : ""}`}>
                  {a.state === "offered" ? "Offered to every school" : a.state === "waiting" ? "Waiting for review" : "Not offered"}</span></td>
                <td className="pa-actions">
                  {a.state !== "offered" && <button type="button" className="portal-link-btn" onClick={() => act(a.id, "offer", a.title)}>Offer to every school</button>}
                  {a.state !== "not offered" && <button type="button" className="portal-link-btn" onClick={() => act(a.id, "withdraw", a.title)}>Withdraw</button>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="lib-muted">Nothing yet.</td></tr>}
          </tbody>
        </table>
      )}
      {adding && (
        <ActivityEditor api={api} stage={adding.stage} subjects={adding.subjects} activityId={null} consentText={adding.consent}
                        isAdmin={true} onClose={() => { setAdding(null); load(); }} onSaved={(t) => say(t)} />
      )}
    </section>
  );
}

function Audit({ api, onError }: { api: Api; onError: (t: string) => void }) {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  useEffect(() => { call<AuditRow[]>(api, "GET", "/platform/audit?limit=300").then(setRows).catch((e) => onError(e.message)); }, [api]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!rows) return <p className="lib-muted">Loading…</p>;
  return (
    <section className="ui-panel">
      <p className="lib-muted">The newest 300 changes across every school. Passwords, UDID and guardian names are never recorded.</p>
      <table className="data-table">
        <caption className="sr-only">Audit trail</caption>
        <thead><tr><th scope="col">When</th><th scope="col">School</th><th scope="col">Who</th><th scope="col">What</th><th scope="col">On</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}><td>{formatWhen(r.at)}</td><td>{r.school || "—"}</td><td className="lib-muted">{r.actor.split(":")[0].replace("_", " ")}</td>
              <td>{r.action.replace(/_/g, " ")}</td><td className="lib-muted">{r.entity}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
