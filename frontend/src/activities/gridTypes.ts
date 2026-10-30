// Shapes returned by /api/v1/teacher/activities-grid (see backend/services/activity_grid.py).

export const ABILITY_KEYS = ["awareness", "sensitivity", "creativity"] as const;
export type AbilityKey = (typeof ABILITY_KEYS)[number];
export const ABILITY_LABEL: Record<AbilityKey, string> = { awareness: "Awareness", sensitivity: "Sensitivity", creativity: "Creativity" };
export const LEVEL_VALUES = ["Beginner", "Proficient", "Advanced"] as const;
export type LevelValue = (typeof LEVEL_VALUES)[number];

export const actKey = (subject: string) => `b_act_${subject}`;
export const levelKey = (subject: string, ability: AbilityKey) => `b_lvl_${subject}_${ability}`;
export const REPLACE_KEY = "b_replace";
export const EACH_SUBJECT = "each_subject";       // quick fill: every subject its own activity for the student's grade

export interface GridStudent {
  student_id: string;
  student_name: string;
  grade: string;
  grade_id?: number | null;
  section: string;
  status: string;
  values: Record<string, string>;
  source: Record<string, "draft" | "portal" | "part_c" | "default" | "">;   // default: the subject's own activity, filled in
  locked: boolean;
  replace: boolean;
  existing: { key: string; name: string; label: string; subject_names: string[]; complete: boolean }[];
  missing_subjects: string[];
  problems: string[];
  notes: string[];
  ready: boolean;
  draft_version: number;
  saved_at: string | null;
}

// subjects / grade_id: where the activity belongs (subjects null: PARAKH's own lists, nothing known)
export interface GridOption { key: string; label: string; subjects?: string[] | null; grade_id?: number | null; grade?: string }

// An activity is offered only under its own subject and to students of its own grade.
export const placedFor = (o: GridOption, subject: string, gradeId?: number | null) =>
  !o.subjects || (o.subjects.includes(subject) && (gradeId == null || o.grade_id === gradeId));

export interface GridData {
  stage: string;
  session: string;
  subjects: { code: string; name: string }[];
  options: GridOption[];
  labels: Record<string, string>;
  students: GridStudent[];
  grades: string[];
  summary: { ready: number; total: number; locked: number };
}

export interface FillResult {
  applied: boolean;
  cells: number;
  students: number;
  kept: number;
  skipped: { student_id: string; student_name: string; reason: string }[];
  subjects: string[];
  no_activity?: string[];           // "Grade 3: The World Around Us" - nothing in the library to fill in
  older_on_parakh?: string[];       // students whose older PARAKH activities would be removed (needs Replace)
  mix_seed?: string | null;         // "Mixed" levels: the deal the preview showed (sent back with the apply)
}

export const gradeOf = (s: Pick<GridStudent, "grade" | "section">) => `${s.grade} - ${s.section}`.replace(/^[\s-]+|[\s-]+$/g, "");
