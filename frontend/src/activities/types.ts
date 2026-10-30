// Shapes returned by /api/v1/activity-library (see backend/services/activity_library.py).

export type Source = "portal_global" | "portal_teacher" | "local";
export type ShareLevel = "private" | "school" | "community";
export type Ability = "awareness" | "sensitivity" | "creativity";
export type Level = "beginner" | "proficient" | "advanced";
export type Rubric = Record<Ability, Record<Level, string>>;

export interface Subject {
  code: string;
  name: string;
}

export interface Activity {
  id: string;
  source: Source;
  stage: string;
  portal_id: number | null;
  code: string;
  title: string;
  label: string;
  activity_text: string;
  assessment_text: string;
  rubric: Rubric;
  goals: string[];
  competencies: string[];
  subjects: string[];
  subject_names: string[];
  covers_all: boolean;
  missing_subjects: string[];
  portal_subject_names: string[];
  grade_id?: number | null;     // PARAKH grade id; for activities made here, chosen by the teacher
  grade_name?: string;
  has_pictures: boolean;
  status: "active" | "disabled";
  is_default: boolean;
  edited: boolean;
  upstream_status: "present" | "removed";
  portal_active: boolean;
  last_synced_at: string | null;
  share_state: "private" | "school" | "community" | "community_ok" | null;
  is_mine: boolean;
  usable_in_excel: boolean;
  not_usable_reason: string;
  can_edit: boolean;
  can_manage: boolean;
  can_delete: boolean;
  can_reset: boolean;
  edited_by_school: boolean;
  edited_by_me: boolean;
  modified: boolean;                  // the texts used on cards differ from PARAKH's
  edit_scope: "me" | "school" | "activity";
  approaches: number[];               // Middle: 1 Art, 2 Sports, 3 Toy, 4 Technology, 5 Any other
  approach_other: string;
  version: number;
  portal_ready: { ok: boolean; missing: string[] };
}

export interface ActivityDetail extends Activity {
  original?: Pick<Activity, "activity_text" | "assessment_text" | "rubric" | "goals" | "competencies" | "subjects" | "subject_names">;
  diff?: { field: string; label: string; original: unknown; current: unknown }[];
  history: { at: string; who: string; action: string }[];
}

export interface CodeOption {
  code: string;
  used_by: number;
  subjects?: string[];          // the subjects PARAKH uses this code for
}

export const APPROACHES: { value: number; label: string }[] = [
  { value: 1, label: "Art-Integrated" }, { value: 2, label: "Sports-Integrated" }, { value: 3, label: "Toy-Based" },
  { value: 4, label: "Technology-Integrated" }, { value: 5, label: "Any other" },
];

export interface SyncJob {
  id: string;
  stages: string[];
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  step: string | null;
  progress: number;
  counts: Record<string, { new: number; updated: number; removed: number; unchanged: number;
                            changed?: { code: string; change: "new" | "changed" | "removed" }[] }> | null;
  automatic?: boolean;                // started by the daily automatic update
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  already_running?: boolean;
}

export interface Listing {
  stage: string;
  subjects: Subject[];
  grades?: { id: number; name: string }[];
  total: number;
  page: number;
  page_size: number;
  items: Activity[];
  counts: { all: number; active: number; disabled: number; covers_all: number; edited: number; removed: number; no_grade?: number; usable_in_excel: number };
  default_id: string | null;
  default_label: string | null;
  sync: { latest: SyncJob | null; last_synced: Record<string, string>; bank_updated?: Record<string, string> };
  consent_text: string;
}

export const STAGES = [
  { id: "Foundational", slug: "foundational", grades: "Balvatika – Grade 2" },
  { id: "Preparatory", slug: "preparatory", grades: "Grades 3 – 5" },
  { id: "Middle", slug: "middle", grades: "Grades 6 – 8" },
] as const;

export const SOURCE_LABEL: Record<Source, string> = {
  portal_global: "PARAKH Activity Bank",
  portal_teacher: "Teacher's own on PARAKH",
  local: "Made in this app",
};

export const ABILITIES: { key: Ability; label: string }[] = [
  { key: "awareness", label: "Awareness" },
  { key: "sensitivity", label: "Sensitivity" },
  { key: "creativity", label: "Creativity" },
];

export const LEVELS: { key: Level; label: string }[] = [
  { key: "beginner", label: "Beginner" },
  { key: "proficient", label: "Proficient" },
  { key: "advanced", label: "Advanced" },
];

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString([], { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
