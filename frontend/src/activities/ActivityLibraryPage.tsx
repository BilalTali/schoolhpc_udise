import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { AlertCircle, BookOpen, Copy, Plus, RefreshCw, Search, Star, Trash2, X } from "lucide-react";
import { ApiError, call, query } from "../api";
import type { Api } from "../api";
import { ActivityEditor } from "./ActivityEditor";
import { CoverageBadge, SourceBadge, StateBadges } from "./Badges";
import { useConfirm } from "./useConfirm";
import { SyncPanel } from "./SyncPanel";
import { STAGES } from "./types";
import type { Activity, Listing } from "./types";

// Activity Library: browse, search and manage activities per stage (route /activities/:stage).

const PAGE_SIZE = 50;
const FILTER_KEYS = ["q", "source", "subject", "covers", "status", "edited", "upstream"] as const;
const yesNo = (v: string | null) => (v === "yes" ? true : v === "no" ? false : undefined);

export function ActivityLibraryPage({ api, isAdmin }: { api: Api; isAdmin: boolean }) {
  const { stage: slug } = useParams();
  const stageInfo = STAGES.find((s) => s.slug === slug);
  if (!stageInfo) return <Navigate to="/activities/preparatory" replace />;
  return <StageLibrary key={stageInfo.id} api={api} isAdmin={isAdmin} stage={stageInfo.id} />;
}

function StageLibrary({ api, isAdmin, stage }: { api: Api; isAdmin: boolean; stage: string }) {
  const [params, setParams] = useSearchParams();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<string | null | undefined>(undefined);   // undefined = closed, null = new
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [search, setSearch] = useState(params.get("q") || "");
  const [confirmUi, confirm] = useConfirm();
  const request = useRef(0);
  const ids = { search: useId(), source: useId(), subject: useId(), covers: useId(), status: useId(), edited: useId(), upstream: useId() };
  const page = Math.max(1, Number(params.get("page") || 1));

  const load = useCallback(async () => {
    const mine = ++request.current;                 // ignore answers to older requests
    setLoading(true);
    setError(null);
    try {
      const data = await call<Listing>(api, "GET", `/activity-library${query({
        stage, page, page_size: PAGE_SIZE, q: params.get("q"), source: params.get("source"), subject: params.get("subject"),
        covers_all: yesNo(params.get("covers")), status: params.get("status"), edited: yesNo(params.get("edited")),
        upstream: params.get("upstream"),
      })}`);
      if (mine === request.current) setListing(data);
    } catch (e: any) {
      if (mine === request.current) setError(e.message);
    } finally {
      if (mine === request.current) setLoading(false);
    }
  }, [api, stage, page, params]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
    setSelected(new Set());
  };
  // Search waits until typing pauses.
  useEffect(() => {
    if (search === (params.get("q") || "")) return;
    const t = window.setTimeout(() => setFilter("q", search), 300);
    return () => window.clearTimeout(t);
  }, [search]);   // eslint-disable-line react-hooks/exhaustive-deps

  const clearFilters = () => {
    setSearch("");
    setParams(new URLSearchParams(), { replace: true });
  };
  const goPage = (p: number) => {
    const next = new URLSearchParams(params);
    next.set("page", String(p));
    setParams(next);
  };
  const anyFilter = FILTER_KEYS.some((k) => params.get(k));

  const say = (text: string, type: "success" | "error" = "success") => setMessage({ type, text });

  const run = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try {
      await fn();
      if (ok) say(ok);
      await load();
    } catch (e: any) {
      say(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  const toggleStatus = async (a: Activity) => {
    const off = a.status === "active";
    if (off && a.is_default && !(await confirm({ title: "Turn off the default activity?", confirmLabel: "Turn off", danger: true,
      message: `"${a.label}" is the default for ${stage}. Turning it off also stops it being the default.` }))) return;
    run(`status-${a.id}`, () => call(api, "PATCH", `/activity-library/${a.id}`, { status: off ? "disabled" : "active" }),
        off ? `"${a.label}" will no longer be offered in Excel.` : `"${a.label}" is offered in Excel again.`);
  };

  const bulk = async (action: "enable" | "disable") => {
    const n = selected.size;
    if (action === "disable" && !(await confirm({ title: `Turn off ${n} activit${n === 1 ? "y" : "ies"}?`, confirmLabel: "Turn off", danger: true,
      message: "They will not be offered in new Excel sheets. Nothing is deleted, and you can turn them on again at any time." }))) return;
    await run("bulk", () => call(api, "POST", "/activity-library/bulk", { ids: [...selected], action }),
              `${n} activit${n === 1 ? "y" : "ies"} turned ${action === "enable" ? "on" : "off"}.`);
    setSelected(new Set());
  };

  const makeDefault = async (a: Activity) => {
    const put = (confirm_partial: boolean) => call(api, "PUT", `/activity-library/defaults/${stage}`, { activity_id: a.id, confirm_partial });
    setBusy(`default-${a.id}`);
    try {
      try {
        await put(false);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 409)) throw e;
        const missing = ((e.detail as any)?.missing_subjects || []) as string[];
        const ok = await confirm({ title: "This activity does not cover every subject", confirmLabel: "Make default anyway",
          message: <>It is not set for: <b>{missing.join(", ")}</b>. Students given only this activity would be missing those subjects. Make it the default anyway?</> });
        if (!ok) return;
        await put(true);
      }
      say(`"${a.label}" is now the default for ${stage}.`);
      await load();
    } catch (e: any) {
      say(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  const clearDefault = () => run("default-clear", () => call(api, "PUT", `/activity-library/defaults/${stage}`, { activity_id: null }),
                                 `${stage} no longer has a default activity.`);

  const duplicate = (a: Activity) => run(`copy-${a.id}`, async () => {
    const made = await call<Activity>(api, "POST", `/activity-library/${a.id}/duplicate`);
    setEditing(made.id);
  }, `A copy of "${a.label}" was made. You can change the copy.`);

  const remove = async (a: Activity) => {
    if (!(await confirm({ title: "Delete this activity?", confirmLabel: "Delete", danger: true,
      message: `"${a.label}" will be removed from the library for good. Excel sheets made earlier keep the name, but it can no longer be chosen.` }))) return;
    run(`delete-${a.id}`, () => call(api, "DELETE", `/activity-library/${a.id}`), `"${a.label}" was deleted.`);
  };

  const items = listing?.items || [];
  const selectable = isAdmin ? items : [];
  const allSelected = selectable.length > 0 && selectable.every((a) => selected.has(a.id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(selectable.map((a) => a.id)));
  const toggleOne = (id: string) => setSelected((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const firstShown = listing && listing.total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const lastShown = listing ? Math.min(page * PAGE_SIZE, listing.total) : 0;
  const pages = listing ? Math.max(1, Math.ceil(listing.total / PAGE_SIZE)) : 1;

  return (
    <div className="lib-page">
      <div className="lib-title-row">
        <div>
          <h1 className="lib-h1"><BookOpen size={24} aria-hidden="true" /> Activity Library</h1>
          <p className="lib-muted">Choose which activities your teachers can pick in the Excel sheet, and which one comes first.</p>
        </div>
        <button type="button" className="btn btn-saffron" onClick={() => setEditing(null)}>
          <Plus size={16} aria-hidden="true" /> Add your own activity
        </button>
      </div>

      <nav className="lib-tabs" aria-label="Stages">
        {STAGES.map((s) => (
          <Link key={s.id} to={`/activities/${s.slug}`} className={`lib-tab ${s.id === stage ? "active" : ""}`}
                aria-current={s.id === stage ? "page" : undefined}>
            <span>{s.id}</span><small>{s.grades}</small>
          </Link>
        ))}
      </nav>

      <SyncPanel api={api} stage={stage} isAdmin={isAdmin} latest={listing?.sync.latest || null}
                 lastSynced={{ ...(listing?.sync.last_synced || {}), ...(listing?.sync.bank_updated || {}) }} onFinished={load} />

      <div className="lib-live" role="status" aria-live="polite">
        {message && (
          <div className={`alert-box alert-${message.type} lib-inline-alert`}>
            {message.type === "error" && <AlertCircle size={18} aria-hidden="true" />}
            <div style={{ flex: 1 }}>{message.text}</div>
            <button type="button" className="icon-btn" aria-label="Dismiss message" onClick={() => setMessage(null)}><X size={16} aria-hidden="true" /></button>
          </div>
        )}
      </div>

      {listing && (
        <dl className="lib-counts">
          <div><dt>Activities</dt><dd>{listing.counts.all}</dd></div>
          <div><dt>Offered in Excel</dt><dd>{listing.counts.usable_in_excel}</dd></div>
          <div><dt>Turned off</dt><dd>{listing.counts.disabled}</dd></div>
          <div><dt>Changed by your school</dt><dd>{listing.counts.edited}</dd></div>
          <div><dt>No longer on PARAKH</dt><dd>{listing.counts.removed}</dd></div>
          <div className="lib-default-count">
            <dt>Default activity</dt>
            <dd>{listing.default_id ? (
              <>{listing.default_label}
                {isAdmin && <button type="button" className="portal-link-btn" onClick={clearDefault}>Remove default</button>}</>
            ) : "None chosen"}</dd>
          </div>
        </dl>
      )}

      <div className="lib-filters" role="search">
        <div className="roster-search-input lib-search">
          <Search size={16} aria-hidden="true" />
          <label htmlFor={ids.search} className="sr-only">Search activities</label>
          <input id={ids.search} type="search" placeholder="Search by code, name or subject" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select id={ids.source} label="Where from" value={params.get("source") || ""} onChange={(v) => setFilter("source", v)}
                options={[["", "All"], ["portal_global", "PARAKH Activity Bank"], ["portal_teacher", "Teacher's own on PARAKH"], ["local", "Made in this app"]]} />
        <Select id={ids.subject} label="Subject" value={params.get("subject") || ""} onChange={(v) => setFilter("subject", v)}
                options={[["", "All subjects"], ...(listing?.subjects || []).map((s) => [s.code, s.name] as [string, string])]} />
        <Select id={ids.covers} label="Covers all subjects" value={params.get("covers") || ""} onChange={(v) => setFilter("covers", v)}
                options={[["", "Any"], ["yes", "Yes, all subjects"], ["no", "No, some missing"]]} />
        <Select id={ids.status} label="In Excel" value={params.get("status") || ""} onChange={(v) => setFilter("status", v)}
                options={[["", "On and off"], ["active", "On"], ["disabled", "Off"]]} />
        <Select id={ids.edited} label="Changed" value={params.get("edited") || ""} onChange={(v) => setFilter("edited", v)}
                options={[["", "Any"], ["yes", "Changed by your school"], ["no", "Not changed"]]} />
        <Select id={ids.upstream} label="On PARAKH" value={params.get("upstream") || ""} onChange={(v) => setFilter("upstream", v)}
                options={[["", "Any"], ["present", "Still on PARAKH"], ["removed", "No longer on PARAKH"]]} />
        {anyFilter && <button type="button" className="btn btn-outline lib-clear" onClick={clearFilters}>Clear filters</button>}
      </div>

      {isAdmin && selected.size > 0 && (
        <div className="lib-bulk" role="region" aria-label="Selected activities">
          <span><b>{selected.size}</b> selected</span>
          <button type="button" className="btn btn-outline" onClick={() => bulk("enable")} disabled={busy === "bulk"}>Turn on</button>
          <button type="button" className="btn btn-outline" onClick={() => bulk("disable")} disabled={busy === "bulk"}>Turn off</button>
          <button type="button" className="portal-link-btn" onClick={() => setSelected(new Set())}>Clear selection</button>
        </div>
      )}

      {error ? (
        <div className="alert-box alert-error" role="alert">
          <AlertCircle size={18} aria-hidden="true" />
          <div>Could not load the activities. {error} <button type="button" className="portal-link-btn" onClick={load}>Try again</button></div>
        </div>
      ) : !listing ? (
        <TableSkeleton />
      ) : listing.counts.all === 0 ? (
        <div className="empty-roster-box">
          <BookOpen size={40} aria-hidden="true" color="#CF4A0A" style={{ margin: "0 auto 0.75rem", opacity: 0.6 }} />
          <h2 className="lib-empty-title">No {stage} activities yet</h2>
          <p className="lib-muted">Use <b>Update {stage}</b> above to bring in the PARAKH Activity Bank, or add an activity of your own.</p>
          <button type="button" className="btn btn-saffron" onClick={() => setEditing(null)}><Plus size={16} aria-hidden="true" /> Add your own activity</button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-roster-box">
          <Search size={32} aria-hidden="true" style={{ margin: "0 auto 0.5rem", opacity: 0.4 }} />
          <h2 className="lib-empty-title">No activities match</h2>
          <button type="button" className="btn btn-outline" onClick={clearFilters}>Clear filters</button>
        </div>
      ) : (
        <>
          <div className="data-table-wrapper lib-table-wrap" aria-busy={loading}>
            <table className="data-table lib-table">
              <caption className="sr-only">{stage} activities, showing {firstShown} to {lastShown} of {listing.total}</caption>
              <thead>
                <tr>
                  {isAdmin && (
                    <th scope="col" className="lib-col-check">
                      <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all activities on this page" />
                    </th>
                  )}
                  <th scope="col">Activity</th>
                  <th scope="col">Subjects</th>
                  <th scope="col">In Excel</th>
                  <th scope="col">Notes</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className={a.status === "disabled" ? "lib-row-off" : ""}>
                    {isAdmin && (
                      <td className="lib-col-check">
                        <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggleOne(a.id)} aria-label={`Select ${a.label}`} />
                      </td>
                    )}
                    <td data-label="Activity">
                      <button type="button" className="lib-name-btn" onClick={() => setEditing(a.id)}>
                        <span className="lib-code">{a.code}</span>
                        {a.title && a.title !== a.code && <span className="lib-title">{a.title}</span>}
                      </button>
                      <SourceBadge source={a.source} />
                    </td>
                    <td data-label="Subjects"><CoverageBadge activity={a} /></td>
                    <td data-label="In Excel">
                      {isAdmin ? (
                        <button type="button" role="switch" aria-checked={a.status === "active"} className="lib-switch"
                                aria-label={`Offer ${a.label} in Excel`} onClick={() => toggleStatus(a)} disabled={busy === `status-${a.id}`}>
                          <span className="lib-switch-track" aria-hidden="true"><span className="lib-switch-dot" /></span>
                          {a.status === "active" ? "On" : "Off"}
                        </button>
                      ) : (
                        <span>{a.status === "active" ? "On" : "Off"}</span>
                      )}
                      {a.status === "active" && !a.usable_in_excel && <div className="lib-reason">{a.not_usable_reason}</div>}
                    </td>
                    <td data-label="Notes"><span className="lib-badges"><StateBadges activity={a} /></span></td>
                    <td className="lib-actions">
                      {isAdmin && !a.is_default && a.usable_in_excel && (
                        <button type="button" className="btn btn-outline lib-act" onClick={() => makeDefault(a)} disabled={busy === `default-${a.id}`}>
                          <Star size={14} aria-hidden="true" /> Make default<span className="sr-only"> ({a.label})</span>
                        </button>
                      )}
                      <button type="button" className="btn btn-outline lib-act" onClick={() => duplicate(a)} disabled={busy === `copy-${a.id}`}>
                        <Copy size={14} aria-hidden="true" /> Copy<span className="sr-only"> {a.label}</span>
                      </button>
                      {a.can_delete && (
                        <button type="button" className="btn btn-outline lib-act lib-act-danger" onClick={() => remove(a)} disabled={busy === `delete-${a.id}`}>
                          <Trash2 size={14} aria-hidden="true" /> Delete<span className="sr-only"> {a.label}</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="lib-pager">
            <span>{loading && <RefreshCw size={13} className="spin" aria-hidden="true" />} Showing {firstShown}–{lastShown} of {listing.total}</span>
            <button type="button" className="btn btn-outline" onClick={() => goPage(page - 1)} disabled={page <= 1}>Previous</button>
            <span>Page {page} of {pages}</span>
            <button type="button" className="btn btn-outline" onClick={() => goPage(page + 1)} disabled={page >= pages}>Next</button>
          </div>
        </>
      )}

      {editing !== undefined && listing && (
        <ActivityEditor api={api} stage={stage} subjects={listing.subjects} activityId={editing} consentText={listing.consent_text}
                        isAdmin={isAdmin} onClose={() => { setEditing(undefined); load(); }} onSaved={(t) => say(t)} />
      )}
      {confirmUi}
    </div>
  );
}

function Select({ id, label, value, onChange, options }: {
  id: string; label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <div className="lib-filter">
      <label htmlFor={id} className="lib-filter-label">{label}</label>
      <select id={id} className="roster-filter-select" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="lib-skeleton" aria-busy="true" aria-label="Loading activities">
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="lib-skeleton-row"><span /><span /><span /></div>)}
    </div>
  );
}
