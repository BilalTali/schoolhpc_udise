// An in-memory stand-in for /api/v1/activity-library, enough for the page's tests.
// Only synthetic activities; no real student or school data.
import type { Activity, ActivityDetail, Listing, SyncJob } from "../activities/types";

export const SUBJECTS = [
  { code: "PSLS1", name: "Language 1 (R1)" }, { code: "PSLS2", name: "Language 2 (R2)" },
  { code: "PSLS3", name: "Mathematics" }, { code: "PSLS4", name: "The World Around Us" },
  { code: "PSLS5", name: "Art Education" }, { code: "PSLS6", name: "Physical Education" },
  { code: "PSLS7", name: "Other Learning Activities" },
];

const rubric = () => ({
  awareness: { beginner: "a-b", proficient: "a-p", advanced: "a-a" },
  sensitivity: { beginner: "s-b", proficient: "s-p", advanced: "s-a" },
  creativity: { beginner: "c-b", proficient: "c-p", advanced: "c-a" },
});

export function makeActivity(over: Partial<Activity> & { id: string; code: string }, isAdmin = true): Activity {
  const subjects = over.subjects ?? SUBJECTS.map((s) => s.code);
  const a: Activity = {
    source: "portal_global", stage: "Preparatory", portal_id: Number(over.id.replace(/\D/g, "")) || 1, title: "",
    label: over.code, activity_text: "Pairs act out a conversation.", assessment_text: "What did you say?",
    rubric: rubric(), goals: ["CG1"], competencies: ["C1.1"], subjects, subject_names: [], covers_all: true,
    missing_subjects: [], portal_subject_names: ["Language 1 (R1)"], has_pictures: false, status: "active",
    is_default: false, edited: false, upstream_status: "present", portal_active: true, last_synced_at: "2026-10-25T10:00:00Z",
    share_state: null, is_mine: false, usable_in_excel: true, not_usable_reason: "", can_edit: isAdmin, can_manage: isAdmin,
    can_delete: false, version: 1, portal_ready: { ok: true, missing: [] }, ...over,
  };
  return withCoverage(a);
}

function withCoverage(a: Activity): Activity {
  const names = Object.fromEntries(SUBJECTS.map((s) => [s.code, s.name]));
  const missing = SUBJECTS.filter((s) => !a.subjects.includes(s.code)).map((s) => s.name);
  return { ...a, subject_names: a.subjects.map((c) => names[c]), missing_subjects: missing, covers_all: missing.length === 0,
           label: a.title && a.title !== a.code ? `${a.code} - ${a.title}` : a.code };
}

export interface Call { method: string; path: string; body?: any }

export function fakeLibraryApi({ isAdmin = true, activities }: { isAdmin?: boolean; activities?: Activity[] } = {}) {
  const state = {
    activities: activities ?? [
      makeActivity({ id: "a1", code: "L1CG 1, C 1.1" }, isAdmin),
      makeActivity({ id: "a2", code: "MCG 1, C 1.2", subjects: ["PSLS1", "PSLS2", "PSLS4", "PSLS6", "PSLS7"] }, isAdmin),
      makeActivity({ id: "a3", code: "TWCG 1, C 1.3", has_pictures: true, usable_in_excel: false,
                     not_usable_reason: "Has pictures - choose it on the PARAKH website instead." }, isAdmin),
    ],
    defaultId: null as string | null,
    job: null as SyncJob | null,
    jobPolls: 0,
    failList: 0,
    calls: [] as Call[],
  };

  const json = (status: number, body: unknown) =>
    Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

  const detail = (a: Activity): ActivityDetail => ({
    ...a, history: [{ at: "2026-10-25T10:00:00Z", who: "Admin", action: "edit" }],
    original: { activity_text: "Pairs act out a conversation.", assessment_text: "What did you say?", rubric: rubric(),
                goals: a.goals, competencies: a.competencies, subjects: SUBJECTS.map((s) => s.code), subject_names: SUBJECTS.map((s) => s.name) },
    diff: a.edited ? [{ field: "activity_text", label: "Activity description", original: "Pairs act out a conversation.", current: a.activity_text }] : [],
  });
  const find = (id: string) => state.activities.find((a) => a.id === id)!;
  const replace = (a: Activity) => { state.activities = state.activities.map((x) => (x.id === a.id ? a : x)); return a; };

  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const path = url.pathname.replace("/api/v1", "");
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    state.calls.push({ method, path: path + url.search, body });
    const p = url.searchParams;

    if (method === "GET" && path === "/activity-library") {
      if (state.failList > 0) { state.failList--; return json(500, { detail: "Database is busy." }); }
      const marked = state.activities.map((a) => ({ ...a, is_default: a.id === state.defaultId }));
      let items = [...marked].sort((a, b) => Number(b.is_default) - Number(a.is_default));
      const q = (p.get("q") || "").toLowerCase();
      if (q) items = items.filter((a) => a.code.toLowerCase().includes(q) || a.subject_names.some((n) => n.toLowerCase().includes(q)));
      if (p.get("covers_all")) items = items.filter((a) => String(a.covers_all) === p.get("covers_all"));
      if (p.get("status")) items = items.filter((a) => a.status === p.get("status"));
      const listing: Listing = {
        stage: "Preparatory", subjects: SUBJECTS, total: items.length, page: 1, page_size: 50, items,
        counts: { all: marked.length, active: marked.filter((a) => a.status === "active").length,
                  disabled: marked.filter((a) => a.status === "disabled").length, covers_all: marked.filter((a) => a.covers_all).length,
                  edited: marked.filter((a) => a.edited).length, removed: 0, usable_in_excel: marked.filter((a) => a.usable_in_excel && a.status === "active").length },
        default_id: state.defaultId, default_label: state.defaultId ? find(state.defaultId).label : null,
        sync: { latest: null, last_synced: { Preparatory: "2026-10-25T10:00:00Z" } },
        consent_text: "I made this activity myself and agree that other teachers may use it.",
      };
      return json(200, listing);
    }
    if (method === "POST" && path === "/activity-library/sync") {
      state.job = { id: "job1", stages: [body?.stage || "all"], status: "RUNNING", step: "Reading Preparatory activities from PARAKH",
                    progress: 10, counts: null, error: null, started_at: null, finished_at: null };
      state.jobPolls = 0;
      return json(202, state.job);
    }
    if (method === "GET" && path === "/activity-library/sync/job1") {
      state.jobPolls++;
      if (state.jobPolls >= 2) {
        state.job = { ...state.job!, status: "COMPLETED", progress: 100, step: "Done",
                      counts: { Preparatory: { new: 2, updated: 1, removed: 1, unchanged: 72 } } };
      } else state.job = { ...state.job!, progress: 50, step: "Reading Preparatory activities from PARAKH (page 1)" };
      return json(200, state.job);
    }
    if (method === "POST" && path === "/activity-library/bulk") {
      for (const id of body.ids) replace({ ...find(id), status: body.action === "enable" ? "active" : "disabled" });
      return json(200, { changed: body.ids });
    }
    if (method === "PUT" && path === "/activity-library/defaults/Preparatory") {
      if (body.activity_id && !find(body.activity_id).covers_all && !body.confirm_partial) {
        return json(409, { detail: { message: "This activity does not cover every subject of the stage.", missing_subjects: find(body.activity_id).missing_subjects } });
      }
      state.defaultId = body.activity_id;
      return json(200, { stage: "Preparatory", activity_id: body.activity_id });
    }
    if (method === "POST" && path === "/activity-library") {
      const made = makeActivity({ id: "new1", code: body.title, title: body.title, source: "local", subjects: body.subjects,
                                  share_state: body.share || "private", is_mine: true, can_edit: true, can_delete: true,
                                  usable_in_excel: false, not_usable_reason: "Made in this app - not on PARAKH yet." }, isAdmin);
      state.activities.push(made);
      return json(201, detail(made));
    }
    const one = path.match(/^\/activity-library\/([^/]+)(\/[a-z]+)?$/);
    if (one) {
      const [, id, action] = one;
      const a = find(id);
      if (!a) return json(404, { detail: "Activity not found." });
      if (method === "GET" && !action) return json(200, detail(a));
      if (method === "PATCH") {
        if (body.version !== undefined && body.version !== a.version) return json(409, { detail: "Someone else changed this activity." });
        const next = withCoverage({ ...a, ...body, rubric: a.rubric, version: a.version + 1,
                                    edited: a.edited || "activity_text" in body || "subjects" in body,
                                    title: body.display_name ?? body.title ?? a.title });
        return json(200, detail(replace(next)));
      }
      if (method === "POST" && action === "/reset") return json(200, detail(replace({ ...a, edited: false, activity_text: "Pairs act out a conversation." })));
      if (method === "POST" && action === "/duplicate") {
        const copy = makeActivity({ id: `${id}copy`, code: `Copy of ${a.code}`, title: `Copy of ${a.code}`, source: "local",
                                    can_edit: true, can_delete: true, is_mine: !isAdmin }, isAdmin);
        state.activities.push(copy);
        return json(201, detail(copy));
      }
      if (method === "POST" && action === "/share") return json(200, detail(replace({ ...a, share_state: body.level })));
      if (method === "DELETE") { state.activities = state.activities.filter((x) => x.id !== id); return json(204, null); }
    }
    return json(404, { detail: `No fake for ${method} ${path}` });
  };

  return { state, fetch: fetchImpl };
}
