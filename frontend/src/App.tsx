import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  School,
  GraduationCap,
  Users,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  Upload,
  Download,
  KeyRound,
  LogOut,
  Building2,
  ShieldCheck,
  RefreshCw,
  Plus,
  UserX,
  FileCheck2,
  Sparkles,
  Check,
  Lock,
  Smartphone,
  Save,
  PlayCircle,
  StopCircle,
  Edit,
  Copy,
  Search,
  Clock,
  Layers,
  FilePenLine,
  BookOpen,
  SlidersHorizontal,
  Menu,
  X,
} from "lucide-react";
import { HpcCardEditor, HpcBulkEntry } from "./HpcCards";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { API_BASE, apiFetch } from "./api";
import { ActivityLibraryPage } from "./activities/ActivityLibraryPage";
import { PlatformAdmin } from "./activities/PlatformAdmin";
import { ActivitiesGrid } from "./activities/ActivitiesGrid";
import { ClassSettings } from "./activities/ClassSettings";
import { TemplatePanel } from "./activities/TemplatePanel";
import { LevelsGrid } from "./activities/LevelsGrid";
import { UploadLive } from "./activities/UploadLive";
import { AllStagesDownload } from "./activities/AllStagesDownload";
import type { LiveJob } from "./activities/UploadLive";
import { OPEN_PARAKH_EVENT } from "./activities/parakhConnect";
import { CaptchaStep } from "./CaptchaStep";
import type { CaptchaResult } from "./CaptchaStep";


// ─── Types ─────────────────────────────────────────────────────────────────

export interface StudentItem {
  student_id: string;
  admission_number: string;
  student_name: string;
  apaar_id?: string;
  hpc_login_id?: string;
  dob?: string;
  gender: string;
  grade: string;
  section: string;
  mother_tongue?: string;
  guardian_name?: string;
  status?: string;
  activity_name?: string;
  activity_subject?: string;
}

interface ValidationReport {
  is_valid: boolean;
  total_records: number;
  detected_stage: string;
  error_count: number;
  warning_count: number;
  errors: { row: number; field: string; message: string }[];
  warnings: { row: number; field: string; message: string }[];
  seeder_working_days: string;
  seeder_max_marks: string;
}

interface UploadJobStatus {
  job_id: string;
  status: string;
  total_students: number;
  success_count: number;
  failed_count: number;
  unverified_count?: number;
  reconciliation_count?: number;
  file_hash?: string;
  detected_stage: string;
}

interface UserInfo {
  role: "SCHOOL_ADMIN" | "TEACHER" | "APP_ADMIN";
  name: string;
  user_id: string;
  school_id?: string;
  school_name?: string;
  udise_code?: string;
  assigned_stage?: string;
  assigned_stages?: string[];
  assigned_grade?: string;
  assigned_grades?: string[];
  assigned_section?: string;
}

interface TeacherItem {
  id: string;
  teacher_name: string;
  username: string;
  employee_code?: string;
  mobile_number?: string;
  assigned_stage: string;
  assigned_stages?: string[];
  assigned_grade: string;
  assigned_grades?: string[];
  assigned_section: string;
  is_active: boolean;
  parakh_connected: boolean;
  parakh_user?: string;
  has_hpc_credentials: boolean;
}


const ALL_STAGES = [
  {
    id: "Foundational",
    label: "Foundational Stage",
    badgeClass: "stage-chip-foundational",
    grades: ["Balvatika", "Grade 1", "Grade 2"],
    desc: "Classes Balvatika – 2 · Ages 3–8"
  },
  {
    id: "Preparatory",
    label: "Preparatory Stage",
    badgeClass: "stage-chip-preparatory",
    grades: ["Grade 3", "Grade 4", "Grade 5"],
    desc: "Classes 3 – 5 · Ages 8–11"
  },
  {
    id: "Middle",
    label: "Middle Stage",
    badgeClass: "stage-chip-middle",
    grades: ["Grade 6", "Grade 7", "Grade 8"],
    desc: "Classes 6 – 8 · Ages 11–14"
  },
  {
    id: "Secondary",
    label: "Secondary Stage",
    badgeClass: "stage-chip-secondary",
    grades: ["Grade 9", "Grade 10", "Grade 11", "Grade 12"],
    desc: "Classes 9 – 12 · Ages 14–18"
  },
];


interface SchoolStats {
  school_name: string;
  udise_code: string;
  total_teachers: number;
  total_jobs: number;
  total_students: number;
  submitted_and_verified: number;
  failed_or_needs_attention: number;
  completion_rate_percent: number;
}

interface HpcStatus {
  logged_in: boolean;
  user?: string;
  school?: string;
  role?: string;
  reason?: string;
  has_credentials?: boolean;
  saved_hpc_login_id?: string;
  stages?: string[];
}

type StatusMsg = { type: "success" | "error" | "info" | "warning"; text: string } | null;
type AuthTab = "admin_login" | "teacher_login" | "register";
type TeacherTab = "roster" | "settings" | "upload" | "bulk" | "activities";

/** Display label and avatar style for a gender value; an empty value is "Not recorded", never guessed. */
function genderInfo(value?: string): { label: string; cls: "male" | "female" | "other" } {
  const g = (value || "").toLowerCase().trim();
  if (["female", "f", "girl", "2"].includes(g)) return { label: "Female", cls: "female" };
  if (["male", "m", "boy", "1"].includes(g)) return { label: "Male", cls: "male" };
  if (g) return { label: "Other", cls: "other" };
  return { label: "Not recorded", cls: "other" };
}

function userFromProfile(p: any): UserInfo {
  const stages = p.assigned_stages?.length ? p.assigned_stages
    : (p.assigned_stage ? String(p.assigned_stage).split(",").map((x: string) => x.trim()).filter(Boolean) : undefined);
  return {
    role: p.role, name: p.name, user_id: p.id, school_id: p.role === "SCHOOL_ADMIN" ? p.id : p.school_id,
    school_name: p.school_name, udise_code: p.udise_code, assigned_stage: p.assigned_stage, assigned_stages: stages,
    assigned_grade: p.assigned_grade, assigned_grades: p.assigned_grades, assigned_section: p.assigned_section,
  };
}

// ─── App ───────────────────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authTab, setAuthTab] = useState<AuthTab>("teacher_login");

  // Auth form
  const [adminIdentifier, setAdminIdentifier] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [appAdminSetup, setAppAdminSetup] = useState<string | null>(null);     // login ID whose first password is being set
  const [setupPassword, setSetupPassword] = useState("");
  const [setupAgain, setSetupAgain] = useState("");
  const [teacherUsername, setTeacherUsername] = useState("");
  const [teacherPassword, setTeacherPassword] = useState("");

  // Register form
  const [regUdise, setRegUdise] = useState("");
  const [regSchoolName, setRegSchoolName] = useState("");
  const [regState, setRegState] = useState("Maharashtra");
  const [regDistrict, setRegDistrict] = useState("Mumbai");
  const [regBlock, setRegBlock] = useState("");
  const [regAdminName, setRegAdminName] = useState("");
  const [regAdminEmail, setRegAdminEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");

  // UI state
  const [statusMsg, setStatusMsg] = useState<StatusMsg>(null);
  const [loading, setLoading] = useState(false);

  // School admin state
  const [teachers, setTeachers] = useState<TeacherItem[]>([]);
  const [schoolStats, setSchoolStats] = useState<SchoolStats | null>(null);
  const [showAddTeacherModal, setShowAddTeacherModal] = useState(false);
  const [newTeacherName, setNewTeacherName] = useState("");
  const [newTeacherUsername, setNewTeacherUsername] = useState("");
  const [newTeacherPassword, setNewTeacherPassword] = useState("");
  const [newTeacherStages, setNewTeacherStages] = useState<string[]>(["Preparatory", "Middle"]);
  const [newTeacherGrades, setNewTeacherGrades] = useState<string[]>(["Grade 3", "Grade 6"]);
  const [newTeacherSection, setNewTeacherSection] = useState("A");

  // Active stage for Teacher Workspace operations
  const [activeTeacherStage, setActiveTeacherStage] = useState<string>("Preparatory");
  const activeTeacherStageRef = useRef(activeTeacherStage);
  activeTeacherStageRef.current = activeTeacherStage;

  // Edit teacher modal state
  const [editingTeacher, setEditingTeacher] = useState<TeacherItem | null>(null);
  const [editTeacherName, setEditTeacherName] = useState("");
  const [editTeacherUsername, setEditTeacherUsername] = useState("");
  const [editTeacherPassword, setEditTeacherPassword] = useState("");
  const [editTeacherStages, setEditTeacherStages] = useState<string[]>([]);
  const [editTeacherGrades, setEditTeacherGrades] = useState<string[]>([]);
  const [editTeacherSection, setEditTeacherSection] = useState("A");
  const [editTeacherActive, setEditTeacherActive] = useState(true);

  // Table password visibility & action state
  const [deletingTeacherId, setDeletingTeacherId] = useState<string | null>(null);

  // HPC Session – School
  const [schoolHpcStatus, setSchoolHpcStatus] = useState<HpcStatus | null>(null);
  const [showSchoolHpcPanel, setShowSchoolHpcPanel] = useState(false);
  const [schoolHpcLoginId, setSchoolHpcLoginId] = useState("");
  const [schoolHpcPassword, setSchoolHpcPassword] = useState("");
  const [schoolHpcLoading, setSchoolHpcLoading] = useState(false);
  const [schoolHpcOtpStep, setSchoolHpcOtpStep] = useState(false);
  const [schoolHpcOtp, setSchoolHpcOtp] = useState("");

  // HPC Session – Teacher
  const [teacherHpcStatus, setTeacherHpcStatus] = useState<HpcStatus | null>(null);
  const [showTeacherHpcPanel, setShowTeacherHpcPanel] = useState(false);
  const [teacherHpcLoginId, setTeacherHpcLoginId] = useState("");
  const [teacherHpcPassword, setTeacherHpcPassword] = useState("");
  const [teacherHpcLoading, setTeacherHpcLoading] = useState(false);
  const [teacherHpcOtpStep, setTeacherHpcOtpStep] = useState(false);
  const [teacherHpcOtp, setTeacherHpcOtp] = useState("");
  const [teacherHpcRefreshing, setTeacherHpcRefreshing] = useState(false);
  const [schoolCaptcha, setSchoolCaptcha] = useState<string | null>(null);     // PARAKH captcha picture to answer
  const [teacherCaptcha, setTeacherCaptcha] = useState<string | null>(null);
  const [teacherHpcRefreshLog, setTeacherHpcRefreshLog] = useState<string | null>(null);
  const [showTeacherRefreshLog, setShowTeacherRefreshLog] = useState(false);

  // Teacher workspace
  const [teacherTab, setTeacherTab] = useState<TeacherTab>("roster");
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);   // the upload shown live on tab 5
  const [navOpen, setNavOpen] = useState(false);                          // the sidebar on small screens
  const location = useLocation();
  const navigate = useNavigate();
  const userRole = user?.role;
  useEffect(() => {                                      // "Connect to PARAKH" on any screen opens the panel
    const open = () => {
      if (userRole === "TEACHER") setShowTeacherHpcPanel(true); else setShowSchoolHpcPanel(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
    window.addEventListener(OPEN_PARAKH_EVENT, open);
    return () => window.removeEventListener(OPEN_PARAKH_EVENT, open);
  }, [userRole]);

  // Student roster states (Teacher)
  const [students, setStudents] = useState<StudentItem[]>([]);
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [fetchJob, setFetchJob] = useState<FetchJob | null>(null);       // "Fetch from PARAKH" running on the server
  const [studentSearch, setStudentSearch] = useState("");
  const [studentGenderFilter, setStudentGenderFilter] = useState("ALL");
  const [studentStatusFilter, setStudentStatusFilter] = useState("ALL");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [openCard, setOpenCard] = useState<{ id: string; name: string } | null>(null);
  const [gridFocus, setGridFocus] = useState<string | undefined>(undefined);   // student to open on the Activities tab

  // School Admin students states
  const [schoolStudents, setSchoolStudents] = useState<StudentItem[]>([]);
  const [schoolStudentsLoading, setSchoolStudentsLoading] = useState(false);
  const [schoolActiveStage, setSchoolActiveStage] = useState<string>("Preparatory");
  const schoolActiveStageRef = useRef(schoolActiveStage);
  schoolActiveStageRef.current = schoolActiveStage;
  const [schoolStudentSearch, setSchoolStudentSearch] = useState("");
  const [schoolTab, setSchoolTab] = useState<"teachers" | "students">("teachers");
  const [schoolRosterLastSynced, setSchoolRosterLastSynced] = useState<string | null>(null);

  // ─── Auth & Session Management ───────────────────────────────────────────

  const handleLogout = useCallback(() => {
    apiFetch("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    setStatusMsg({ type: "info", text: "Logged out successfully." });
  }, []);

  const handleUnauthorized = useCallback(() => {
    setUser(null);
    setStatusMsg({ type: "error", text: "Your session has expired. Please log in again." });
  }, []);

  // ─── API Helpers ─────────────────────────────────────────────────────────

  // The session is an httpOnly cookie; apiFetch adds the CSRF header and renews the session once.
  const apiGet = useCallback(async (path: string) => {
    const res = await apiFetch(path);
    if (res.status === 401) {
      handleUnauthorized();
    }
    return res;
  }, [handleUnauthorized]);

  const apiPost = useCallback(async (path: string, body?: any) => {
    const res = await apiFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
      handleUnauthorized();
    }
    return res;
  }, [handleUnauthorized]);

  const cardsApi = useMemo(
    () => ({ base: API_BASE, onUnauthorized: handleUnauthorized }),
    [handleUnauthorized],
  );

  // ─── Data Loaders ────────────────────────────────────────────────────────

  const fetchSchoolData = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const [statsRes, teachersRes] = await Promise.all([
        apiGet("/school/stats"),
        apiGet("/school/teachers"),
      ]);
      if (statsRes.ok) setSchoolStats(await statsRes.json());
      if (teachersRes.ok) setTeachers(await teachersRes.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [user, apiGet]);

  const fetchSchoolHpcStatus = useCallback(async () => {
    if (!user || user.role !== "SCHOOL_ADMIN") return;
    try {
      const res = await apiGet("/school/hpc/status");
      if (res.ok) {
        const data: HpcStatus = await res.json();
        setSchoolHpcStatus(data);
        if (data.saved_hpc_login_id) {
          setSchoolHpcLoginId(data.saved_hpc_login_id);
        }
      }
    } catch (e) {
      console.error(e);
    }
  }, [user, apiGet]);

  const fetchTeacherHpcStatus = useCallback(async () => {
    if (!user || user.role !== "TEACHER") return;
    try {
      const res = await apiGet("/teacher/hpc/status");
      if (res.ok) {
        const data: HpcStatus = await res.json();
        setTeacherHpcStatus(data);
        if (data.saved_hpc_login_id) setTeacherHpcLoginId(data.saved_hpc_login_id);
      }
    } catch (e) {
      console.error(e);
    }
  }, [user, apiGet]);

  const loadTeacherRoster = useCallback(async (stageToFetch?: string) => {
    if (!user || user.role !== "TEACHER") return;
    const stage = stageToFetch || activeTeacherStageRef.current || "Preparatory";
    setStudentsLoading(true);
    try {
      const res = await apiGet(`/teacher/roster?stage=${encodeURIComponent(stage)}`);
      if (res.ok) {
        const data = await res.json();
        setStudents(data.students || []);
      }
    } catch (err: any) {
      console.error("Failed to load cached roster", err);
    } finally {
      setStudentsLoading(false);
    }
  }, [user, apiGet]);

  const loadSchoolRoster = useCallback(async (stageToFetch?: string) => {
    if (!user || user.role !== "SCHOOL_ADMIN") return;
    const stage = stageToFetch || schoolActiveStageRef.current || "Preparatory";
    setSchoolStudentsLoading(true);
    try {
      const res = await apiGet(`/school/roster?stage=${encodeURIComponent(stage)}`);
      if (res.ok) {
        const data = await res.json();
        setSchoolStudents(data.students || []);
        setSchoolRosterLastSynced(data.last_synced_at || null);
      }
    } catch (err: any) {
      console.error("Failed to load school roster", err);
    } finally {
      setSchoolStudentsLoading(false);
    }
  }, [user, apiGet]);

  const handleSyncSchoolRoster = async () => {
    if (!user || user.role !== "SCHOOL_ADMIN") return;
    setSchoolStudentsLoading(true);
    setStatusMsg({ type: "info", text: `Syncing ${schoolActiveStage} students from PARAKH portal...` });
    try {
      const res = await apiPost(`/school/roster/sync?stage=${encodeURIComponent(schoolActiveStage)}`);
      const data = await res.json();
      if (res.ok) {
        setSchoolStudents(data.students || []);
        setSchoolRosterLastSynced(data.last_synced_at || null);
        setStatusMsg({ type: "success", text: `Synced ${data.total_students} students for ${schoolActiveStage} Stage!` });
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Failed to sync from portal." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setSchoolStudentsLoading(false);
    }
  };

  const teacherStagesList = (): string[] => {
    if (!user) return [];
    return teacherHpcStatus?.stages && teacherHpcStatus.stages.length > 0
      ? teacherHpcStatus.stages
      : user.assigned_stages && user.assigned_stages.length > 0
        ? user.assigned_stages
        : (user.assigned_stage || "Preparatory").split(",").map((s) => s.trim()).filter(Boolean);
  };

  const renderTeacherStageSwitcher = () => {
    if (!user) return null;
    const teacherStages = teacherStagesList();
    if (teacherStages.length > 1) {
      return (
        <div className="stage-switch-bar">
          <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--chakra-navy)", marginLeft: "0.4rem", marginRight: "0.3rem" }}>
            Select Stage:
          </span>
          {teacherStages.map((stg) => (
            <button
              key={stg}
              type="button"
              className={`stage-switch-btn ${activeTeacherStage === stg ? "active" : ""}`}
              onClick={() => {
                setActiveTeacherStage(stg);
                loadTeacherRoster(stg);
              }}
            >
              {stg} Stage
            </button>
          ))}
        </div>
      );
    }
    return null;
  };

  // ─── Init ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    localStorage.removeItem("hpc_auth_session");      // older versions kept the login token here
    apiFetch("/auth/me")
      .then(async (res) => { if (res.ok) setUser(userFromProfile(await res.json())); })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!user) return;
    if (user.role === "SCHOOL_ADMIN") {
      fetchSchoolData();
      fetchSchoolHpcStatus();
      loadSchoolRoster(schoolActiveStageRef.current);
    } else if (user.role === "TEACHER") {
      fetchTeacherHpcStatus();
      let initStage = "Preparatory";
      if (user.assigned_stages && user.assigned_stages.length > 0) {
        initStage = user.assigned_stages[0];
      } else if (user.assigned_stage) {
        const first = user.assigned_stage.split(",")[0].trim();
        if (first) initStage = first;
      }
      setActiveTeacherStage(initStage);
      loadTeacherRoster(initStage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id, user?.role]);

  const handleCreateTeacher = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    if (newTeacherStages.length === 0) {
      setStatusMsg({ type: "error", text: "Please select at least one HPC Stage (e.g., Preparatory, Middle)." });
      return;
    }
    if (newTeacherGrades.length === 0) {
      setStatusMsg({ type: "error", text: "Please select at least one assigned Class / Grade." });
      return;
    }
    setLoading(true);
    setStatusMsg(null);
    try {
      const res = await apiPost("/school/teachers", {
        teacher_name: newTeacherName,
        username: newTeacherUsername,
        password: newTeacherPassword,
        assigned_stage: newTeacherStages.join(", "),
        assigned_stages: newTeacherStages,
        assigned_grade: newTeacherGrades.join(", "),
        assigned_grades: newTeacherGrades,
        assigned_section: newTeacherSection,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: `Teacher '${data.teacher_name}' created for ${data.assigned_stage} (${data.assigned_grade})!` });
        setShowAddTeacherModal(false);
        setNewTeacherName(""); setNewTeacherUsername(""); setNewTeacherPassword("");
        setNewTeacherStages(["Preparatory", "Middle"]);
        setNewTeacherGrades(["Grade 3", "Grade 6"]);
        fetchSchoolData();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Failed to create teacher." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };


  const confirmDeleteTeacher = async (teacherId: string) => {
    if (!user) return;
    try {
      const res = await apiFetch(`/school/teachers/${teacherId}`, {
        method: "DELETE",
      });
      if (res.status === 401) {
        handleUnauthorized();
        return;
      }
      if (res.ok) {
        setStatusMsg({ type: "success", text: "Teacher switched off. Their upload history is kept; switch them on again with Edit." });
        setDeletingTeacherId(null);
        fetchSchoolData();
      } else {
        const data = await res.json().catch(() => ({}));
        setStatusMsg({ type: "error", text: data.detail || "Failed to remove teacher." });
        setDeletingTeacherId(null);
      }
    } catch (e: any) {
      console.error(e);
      setStatusMsg({ type: "error", text: e.message || "Failed to remove teacher." });
      setDeletingTeacherId(null);
    }
  };

  const openEditModal = (t: TeacherItem) => {
    setEditingTeacher(t);
    setEditTeacherName(t.teacher_name);
    setEditTeacherUsername(t.username);
    setEditTeacherPassword("");
    const stages = t.assigned_stages && t.assigned_stages.length > 0
      ? t.assigned_stages
      : (t.assigned_stage || "Preparatory").split(",").map((s) => s.trim()).filter(Boolean);
    setEditTeacherStages(stages);
    const grades = t.assigned_grades && t.assigned_grades.length > 0
      ? t.assigned_grades
      : (t.assigned_grade || "").split(",").map((g) => g.trim()).filter(Boolean);   // none set: none shown (L-5)
    setEditTeacherGrades(grades);
    setEditTeacherSection(t.assigned_section || "");
    setEditTeacherActive(t.is_active);
  };

  const toggleEditStage = (stgId: string) => {
    setEditTeacherStages((prev) => {
      const exists = prev.includes(stgId);
      const next = exists ? prev.filter((s) => s !== stgId) : [...prev, stgId];
      if (next.length === 0) return [stgId];
      const validGrades = ALL_STAGES.filter((s) => next.includes(s.id)).flatMap((s) => s.grades);
      setEditTeacherGrades((prevGrades) => {
        const kept = prevGrades.filter((g) => validGrades.includes(g));
        return kept.length > 0 ? kept : (validGrades.length > 0 ? [validGrades[0]] : ["Grade 3"]);
      });
      return next;
    });
  };

  const toggleEditGrade = (grade: string) => {
    setEditTeacherGrades((prev) => {
      const exists = prev.includes(grade);
      const next = exists ? prev.filter((g) => g !== grade) : [...prev, grade];
      return next.length > 0 ? next : [grade];
    });
  };

  const handleUpdateTeacher = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !editingTeacher) return;
    setLoading(true);
    setStatusMsg(null);
    try {
      const body: any = {
        teacher_name: editTeacherName.trim(),
        username: editTeacherUsername.trim().toLowerCase(),
        assigned_stage: editTeacherStages.join(", "),
        assigned_stages: editTeacherStages,
        assigned_grade: editTeacherGrades.join(", "),
        assigned_grades: editTeacherGrades,
        assigned_section: editTeacherSection,
        is_active: editTeacherActive,
      };
      if (editTeacherPassword.trim()) {
        body.password = editTeacherPassword.trim();
      }
      const res = await apiFetch(`/school/teachers/${editingTeacher.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: `Teacher '${data.teacher_name}' updated successfully!` });
        setEditingTeacher(null);
        fetchSchoolData();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Failed to update teacher." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setStatusMsg({ type: "info", text: `Copied ${label} to clipboard: "${text}"` });
  };


  // ─── School HPC Session ───────────────────────────────────────────────────

  const handleSaveSchoolHpcCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setSchoolHpcLoading(true);
    try {
      const res = await apiPost("/school/hpc/save-credentials", {
        hpc_login_id: schoolHpcLoginId.trim(),
        hpc_password: schoolHpcPassword,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: "✅ HPC credentials saved! Now click 'Start Session'." });
        fetchSchoolHpcStatus();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Save failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setSchoolHpcLoading(false);
    }
  };

  const handleStartSchoolSession = async () => {
    setSchoolHpcLoading(true);
    setStatusMsg({ type: "info", text: "Connecting to PARAKH…" });
    try {
      const body: any = {};
      const isDashboardCred =
        (adminIdentifier && schoolHpcLoginId.trim().toLowerCase() === adminIdentifier.trim().toLowerCase()) ||
        (user?.udise_code && schoolHpcLoginId.trim() === user.udise_code.trim()) ||
        (user?.user_id && schoolHpcLoginId.trim() === user.user_id.trim());

      if (schoolHpcStatus?.has_credentials) {
        if (isDashboardCred || !schoolHpcLoginId.trim() || schoolHpcLoginId.trim() === schoolHpcStatus.saved_hpc_login_id) {
          // Use saved HPC credentials; restore inputs if browser autofill altered them
          if (schoolHpcStatus.saved_hpc_login_id) setSchoolHpcLoginId(schoolHpcStatus.saved_hpc_login_id);
          // Empty body tells backend to use saved DB credentials
        } else {
          // Explicit manual override
          body.hpc_login_id = schoolHpcLoginId.trim();
          body.hpc_password = schoolHpcPassword;
        }
      } else {
        if (schoolHpcLoginId) body.hpc_login_id = schoolHpcLoginId.trim();
        if (schoolHpcPassword) body.hpc_password = schoolHpcPassword;
      }

      const res = await apiPost("/school/hpc/start-session", body);
      const data = await res.json();
      if (res.ok) {
        if (data.status === "captcha_required") {
          setSchoolCaptcha(data.captcha_image);
          setStatusMsg({ type: "info", text: "Type the answer shown in the picture to connect." });
        } else if (data.status === "otp_required") {
          setSchoolHpcOtpStep(true);
          setStatusMsg({ type: "info", text: "📱 OTP sent to your registered mobile. Enter it below." });
        } else if (data.status === "authenticated") {
          setStatusMsg({ type: "success", text: `🎉 HPC session started! Connected as ${data.user}` });
          setSchoolHpcOtpStep(false);
          fetchSchoolHpcStatus();
        }
      } else {
        setStatusMsg({ type: "error", text: data.detail || "HPC login failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setSchoolHpcLoading(false);
    }
  };

  const handleVerifySchoolOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setSchoolHpcLoading(true);
    try {
      const res = await apiPost("/school/hpc/verify-otp", { otp: schoolHpcOtp });
      const data = await res.json();
      if (res.ok && data.status === "authenticated") {
        setStatusMsg({ type: "success", text: `🎉 OTP verified! HPC session active for ${data.user}.` });
        setSchoolHpcOtpStep(false);
        setSchoolHpcOtp("");
        fetchSchoolHpcStatus();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Invalid OTP." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setSchoolHpcLoading(false);
    }
  };

  const afterCaptcha = (who: "school" | "teacher", result: CaptchaResult) => {
    (who === "school" ? setSchoolCaptcha : setTeacherCaptcha)(null);
    if (result.status === "otp_required") {
      (who === "school" ? setSchoolHpcOtpStep : setTeacherHpcOtpStep)(true);
      setStatusMsg({ type: "info", text: "📱 OTP sent to your registered mobile. Enter it below." });
    } else {
      setStatusMsg({ type: "success", text: `Connected to PARAKH as ${result.user || "you"}.` });
      (who === "school" ? fetchSchoolHpcStatus : fetchTeacherHpcStatus)();
    }
  };

  const handleEndSchoolSession = async () => {
    setSchoolHpcLoading(true);
    try {
      await apiPost("/school/hpc/end-session");
      setStatusMsg({ type: "info", text: "HPC session ended." });
      setSchoolHpcOtpStep(false);
      fetchSchoolHpcStatus();
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setSchoolHpcLoading(false);
    }
  };

  // ─── Teacher HPC Session ──────────────────────────────────────────────────


  const handleSaveTeacherHpcCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setTeacherHpcLoading(true);
    try {
      const res = await apiPost("/teacher/hpc/save-credentials", {
        hpc_login_id: teacherHpcLoginId.trim(),
        hpc_password: teacherHpcPassword,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: "✅ HPC credentials saved! Now click 'Start Session'." });
        fetchTeacherHpcStatus();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Save failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setTeacherHpcLoading(false);
    }
  };

  const handleStartTeacherSession = async () => {
    setTeacherHpcLoading(true);
    setStatusMsg({ type: "info", text: "Connecting to PARAKH…" });
    try {
      const body: any = {};
      const isDashboardCred =
        (teacherUsername && teacherHpcLoginId.trim().toLowerCase() === teacherUsername.trim().toLowerCase()) ||
        (user?.user_id && teacherHpcLoginId.trim() === user.user_id.trim());

      if (teacherHpcStatus?.has_credentials) {
        if (isDashboardCred || !teacherHpcLoginId.trim() || teacherHpcLoginId.trim() === teacherHpcStatus.saved_hpc_login_id) {
          if (teacherHpcStatus.saved_hpc_login_id) setTeacherHpcLoginId(teacherHpcStatus.saved_hpc_login_id);
        } else {
          body.hpc_login_id = teacherHpcLoginId.trim();
          body.hpc_password = teacherHpcPassword;
        }
      } else {
        if (teacherHpcLoginId) body.hpc_login_id = teacherHpcLoginId.trim();
        if (teacherHpcPassword) body.hpc_password = teacherHpcPassword;
      }

      const res = await apiPost("/teacher/hpc/start-session", body);
      const data = await res.json();
      if (res.ok) {
        if (data.status === "captcha_required") {
          setTeacherCaptcha(data.captcha_image);
          setStatusMsg({ type: "info", text: "Type the answer shown in the picture to connect." });
        } else if (data.status === "otp_required") {
          setTeacherHpcOtpStep(true);
          setStatusMsg({ type: "info", text: "📱 OTP sent to your registered mobile. Enter it below." });
        } else if (data.status === "authenticated") {
          setStatusMsg({ type: "success", text: `🎉 HPC session started! Connected as ${data.user}` });
          setTeacherHpcOtpStep(false);
          fetchTeacherHpcStatus();
        }
      } else {
        setStatusMsg({ type: "error", text: data.detail || "HPC login failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setTeacherHpcLoading(false);
    }
  };

  const handleVerifyTeacherOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setTeacherHpcLoading(true);
    try {
      const res = await apiPost("/teacher/hpc/verify-otp", { otp: teacherHpcOtp });
      const data = await res.json();
      if (res.ok && data.status === "authenticated") {
        setStatusMsg({ type: "success", text: `🎉 OTP verified! HPC session active for ${data.user}.` });
        setTeacherHpcOtpStep(false);
        setTeacherHpcOtp("");
        fetchTeacherHpcStatus();
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Invalid OTP." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setTeacherHpcLoading(false);
    }
  };

  const handleEndTeacherSession = async () => {
    setTeacherHpcLoading(true);
    try {
      await apiPost("/teacher/hpc/end-session");
      setStatusMsg({ type: "info", text: "HPC session ended." });
      setTeacherHpcOtpStep(false);
      fetchTeacherHpcStatus();
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setTeacherHpcLoading(false);
    }
  };

  const handleRefreshTeacherSession = async () => {
    setTeacherHpcRefreshing(true);
    setTeacherHpcRefreshLog(null);
    setShowTeacherRefreshLog(false);
    setStatusMsg({ type: "info", text: "Reconnecting to PARAKH…" });
    try {
      const res = await apiPost("/teacher/hpc/refresh-session");
      const data = await res.json();
      if (res.ok) {
        setTeacherHpcRefreshLog(data.log || "");
        setShowTeacherRefreshLog(!!data.log);
        if (data.status === "captcha_required") {
          setTeacherCaptcha(data.captcha_image);
          setStatusMsg({ type: "info", text: "Type the answer shown in the picture to reconnect." });
        } else if (data.success) {
          setStatusMsg({ type: "success", text: "✅ PARAKH session refreshed! Fresh credentials saved." });
          fetchTeacherHpcStatus();
        } else {
          setStatusMsg({ type: "warning", text: "⚠️ Session refresh ran — check the log below for details." });
        }
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Refresh failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setTeacherHpcRefreshing(false);
    }
  };

  // ─── Teacher Roster & Upload ──────────────────────────────────────────────

  // "Fetch from PARAKH" runs on the server for a few minutes; the page follows it and shows the progress.
  const fetchTimer = useRef<number | undefined>(undefined);
  const followFetch = useCallback(function follow(stage: string, listed = false) {
    window.clearTimeout(fetchTimer.current);
    fetchTimer.current = window.setTimeout(async () => {
      try {
        const res = await apiGet("/teacher/roster/sync");
        if (!res.ok) { follow(stage, listed); return; }
        const { job } = await res.json() as { job: FetchJob | null };
        setFetchJob(job);
        if (!job) return;
        if (!listed && job.rosters?.[stage] !== undefined) {   // the class list is in: show the names now
          loadTeacherRoster(stage);
          listed = true;
        }
        if (job.status === "RUNNING") { follow(stage, listed); return; }
        loadTeacherRoster(stage);
        setStatusMsg(job.status === "COMPLETED"
          ? job.notes?.length
            ? { type: "warning", text: `Fetched from PARAKH - ${job.summary}. ${job.notes.join(" ")}` }
            : { type: "success", text: `Fetched from PARAKH - ${job.summary}. Every screen now opens straight away.` }
          : { type: "error", text: `The fetch stopped: ${job.error || "PARAKH did not answer"}. The list below is what was read before.` });
      } catch {
        follow(stage, listed);                          // a missed check is tried again; the fetch goes on
      }
    }, 1500);
  }, [apiGet]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => window.clearTimeout(fetchTimer.current), []);

  const handleSyncRoster = async (stageOverride?: string) => {
    const stageToUse = stageOverride || activeTeacherStage || "Preparatory";
    setStatusMsg(null);
    try {
      const res = await apiPost(`/teacher/roster/sync?stage=${encodeURIComponent(stageToUse)}`);
      const data = await res.json();
      if (!res.ok) {
        setStatusMsg({ type: "error", text: data.detail || "The fetch could not start." });
        if (res.status === 409) { setShowTeacherHpcPanel(true); window.scrollTo({ top: 0, behavior: "smooth" }); }
        return;
      }
      setFetchJob(data);
      followFetch(stageToUse);
    } catch (e: any) {
      setStatusMsg({ type: "error", text: e.message });
    }
  };

  const handleDownloadExcel = async (stageOverride?: string) => {
    const stageToUse = stageOverride || activeTeacherStage || "Preparatory";
    setLoading(true);
    try {
      const res = await apiFetch(`/teacher/roster/download?stage=${encodeURIComponent(stageToUse)}`, {
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "HPC_Class_Workbook.xlsx";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        setStatusMsg({ type: "success", text: "Excel workbook downloaded (all your stages)." });
      } else {
        const err = await res.json().catch(() => ({}));
        setStatusMsg({ type: "error", text: err.detail || "Download failed." });
      }
    } catch (e: any) {
      setStatusMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };


  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !user) return;
    setValidationReport(null);
    if (!isSubmitting) setActiveJobId(null);           // a finished upload's live view makes way for the new file
    setLoading(true);
    setStatusMsg(null);
    setUploadedFileName(file.name);

    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await apiFetch(`/teacher/upload/validate`, {
        method: "POST",
        body: formData,
      });
      if (res.status === 401) {
        handleUnauthorized();
        return;
      }
      const report = await res.json();
      if (res.ok) {
        setValidationReport(report);
        setStatusMsg(report.is_valid
          ? { type: "success", text: `Pre-flight passed! ${report.total_records} students ready.` }
          : { type: "error", text: `${report.error_count} validation error(s) found.` });
      } else {
        setStatusMsg({ type: "error", text: report.detail || "Failed to parse workbook." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleStartSubmission = async () => {
    if (!user || !uploadedFileName) return;
    setIsSubmitting(true);
    setStatusMsg({ type: "info", text: "Initiating automated submission to PARAKH portal..." });
    try {
      const res = await apiFetch(`/teacher/upload/submit?file_name=${encodeURIComponent(uploadedFileName)}`, {
        method: "POST",
      });
      if (res.status === 401) {
        handleUnauthorized();
        setIsSubmitting(false);
        return;
      }
      const job = await res.json();
      if (res.ok) {
        setStatusMsg(null);
        setActiveJobId(String(job.job_id || ""));         // UploadLive follows it step by step
      } else {
        setStatusMsg({ type: "error", text: job.detail || "Submission failed." });
        setIsSubmitting(false);
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
      setIsSubmitting(false);
    }
  };

  const afterUpload = (job: LiveJob) => {
    setIsSubmitting(false);
    const skipped = job.students.filter((st) => st.status === "SKIPPED").length;
    if (job.status === "COMPLETED") {
      setStatusMsg({ type: "success", text: `All ${job.success_count} students were saved to PARAKH.${skipped ? ` ${skipped} skipped (Sync = No).` : ""}` });
    } else if (job.status === "PARTIAL_SUCCESS") {
      setStatusMsg({ type: "warning", text: `${job.success_count} saved, ${job.failed_count} not saved. Those PARAKH did not take can be retried below; rows with a mistake need the file fixed and uploaded again.` });
    } else {
      setStatusMsg({ type: "error", text: "Nothing was saved. See the reasons below; check the PARAKH connection and try again." });
    }
  };

  // A fetch from PARAKH still running (for example after a page reload) is followed again.
  useEffect(() => {
    if (!user || user.role !== "TEACHER") return;
    apiFetch("/teacher/roster/sync")
      .then(async (res) => {
        if (!res.ok) return;
        const { job } = await res.json() as { job: FetchJob | null };
        if (job?.status === "RUNNING") { setFetchJob(job); followFetch(activeTeacherStage || "Preparatory", true); }
      })
      .catch(() => undefined);
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  // An upload still running (for example after a page reload) is shown live again.
  useEffect(() => {
    if (!user || user.role !== "TEACHER") return;
    apiFetch("/teacher/upload/jobs")
      .then(async (res) => {
        if (!res.ok) return;
        const jobs: UploadJobStatus[] = await res.json();
        const running = jobs.find((j) => j.status === "PENDING" || j.status === "IN_PROGRESS");
        if (running) {
          setActiveJobId(String(running.job_id));
          setIsSubmitting(true);
        }
      })
      .catch(() => undefined);
  }, [user]);

  // ─── Auth ─────────────────────────────────────────────────────────────────

  const handleLogin = async (e: React.FormEvent, role: "SCHOOL_ADMIN" | "TEACHER") => {
    e.preventDefault();
    setLoading(true);
    setStatusMsg(null);
    const identifier = role === "SCHOOL_ADMIN" ? adminIdentifier.trim() : teacherUsername.trim();
    const password = role === "SCHOOL_ADMIN" ? adminPassword : teacherPassword;
    try {
      const res = await apiFetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier, password, role }),
      });
      const data = await res.json();
      if (res.ok) {
        const stagesList = data.assigned_stages && data.assigned_stages.length > 0
          ? data.assigned_stages
          : (data.assigned_stage ? data.assigned_stage.split(",").map((s: string) => s.trim()).filter(Boolean) : ["Preparatory"]);
        const gradesList = data.assigned_grades && data.assigned_grades.length > 0
          ? data.assigned_grades
          : (data.assigned_grade ? data.assigned_grade.split(",").map((g: string) => g.trim()).filter(Boolean) : []);

        const userInfo: UserInfo = {
          role: data.role,
          name: data.name,
          user_id: data.user_id,
          school_id: data.school_id,
          school_name: data.school_name,
          udise_code: data.udise_code,
          assigned_stage: data.assigned_stage,
          assigned_stages: stagesList,
          assigned_grade: data.assigned_grade,
          assigned_grades: gradesList,
          assigned_section: data.assigned_section,
        };
        setUser(userInfo);
        setStatusMsg({ type: "success", text: `Welcome back, ${data.name}!` });
      } else if (res.status === 409 && data.detail?.setup_required) {
        setAppAdminSetup(identifier);                  // the application admin's first sign-in: set the password
        setStatusMsg({ type: "warning", text: data.detail.message });
      } else {
        setStatusMsg({ type: "error", text: typeof data.detail === "string" ? data.detail : data.detail?.message || "Invalid credentials." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleAppAdminSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setStatusMsg(null);
    try {
      const res = await apiFetch("/auth/app-admin/setup", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: appAdminSetup, password: setupPassword }),
      });
      const data = await res.json();
      if (res.ok) {
        setAppAdminSetup(null);
        setAdminPassword("");
        setSetupPassword("");
        setSetupAgain("");
        setStatusMsg({ type: "success", text: "Password set. Sign in with the login ID and this password." });
      } else {
        const d = data.detail;
        setStatusMsg({ type: "error", text: Array.isArray(d) ? "Use at least 12 characters." : (d || "The password could not be set.") });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleSchoolRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setStatusMsg(null);
    if (!/^\d{11}$/.test(regUdise.trim())) {
      setStatusMsg({ type: "error", text: "UDISE Code must be exactly 11 numeric digits." });
      setLoading(false);
      return;
    }
    try {
      const res = await apiFetch(`/auth/school/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          udise_code: regUdise.trim(),
          school_name: regSchoolName.trim(),
          state: regState.trim(),
          district: regDistrict.trim(),
          block: regBlock.trim() || null,
          admin_name: regAdminName.trim(),
          admin_email: regAdminEmail.trim(),
          password: regPassword,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: `School '${data.school_name}' registered! Please log in.` });
        setAuthTab("admin_login");
        setAdminIdentifier(regUdise.trim());
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Registration failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setLoading(false);
    }
  };


  // ─── Sub-components ───────────────────────────────────────────────────────

  /** Reusable HPC Session Panel shown on both dashboards */
  const HpcSessionPanel = ({
    role,
    hpcStatus,
    loading: hpcLoad,
    loginId, setLoginId,
    password: pwd, setPassword,
    otpStep, otp, setOtp,
    onSaveCredentials,
    onStartSession,
    onVerifyOtp,
    onEndSession,
    onRefreshStatus,
    showPanel, setShowPanel,
  }: {
    role: "school" | "teacher";
    hpcStatus: HpcStatus | null;
    loading: boolean;
    loginId: string; setLoginId: (v: string) => void;
    password: string; setPassword: (v: string) => void;
    otpStep: boolean; otp: string; setOtp: (v: string) => void;
    onSaveCredentials: (e: React.FormEvent) => void;
    onStartSession: () => void;
    onVerifyOtp: (e: React.FormEvent) => void;
    onEndSession: () => void;
    onRefreshStatus: () => void;
    showPanel: boolean; setShowPanel: (v: boolean) => void;
  }) => {
    const isActive = hpcStatus?.logged_in;

    const whose = role === "school" ? "the school's" : "your own";
    return (
      <section className="ui-panel conn-panel" aria-label="PARAKH connection">
        <div className="conn-head">
          <div className={`conn-status ${isActive ? "on" : "off"}`}>
            <span className="dot" aria-hidden="true" />
            <div>
              <b>{isActive ? "Connected to PARAKH" : "Not connected to PARAKH"}</b>
              <small>{isActive
                ? `Signed in as ${hpcStatus?.user || "PARAKH user"}${hpcStatus?.school ? ` · ${hpcStatus.school}` : ""}`
                : `Connect with ${whose} PARAKH login. You type the captcha once; the connection then stays open.`}</small>
            </div>
          </div>
          <div className="conn-actions">
            <button type="button" className="btn btn-outline btn-sm" onClick={onRefreshStatus} title="Check the connection again">
              <RefreshCw size={14} aria-hidden="true" /> Check
            </button>
            {isActive && (
              <button type="button" className="btn btn-outline btn-sm btn-danger-outline" onClick={onEndSession} disabled={hpcLoad}>
                <StopCircle size={14} aria-hidden="true" /> Disconnect
              </button>
            )}
            <button type="button" className="icon-close" onClick={() => setShowPanel(false)} aria-label="Close"><X size={18} /></button>
          </div>
        </div>

        {showPanel && (
          <div className="conn-body">
            {otpStep ? (
              <form onSubmit={onVerifyOtp} className="conn-otp">
                <div className="alert-box alert-info">
                  <Smartphone size={18} aria-hidden="true" />
                  <div><b>One more step.</b> Enter the code PARAKH sent to your registered mobile.</div>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor={`otp_${role}`}>Code from SMS</label>
                  <input id={`otp_${role}`} type="text" inputMode="numeric" maxLength={8} className="form-input conn-otp-input" placeholder="••••••"
                         value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} required autoFocus />
                </div>
                <div className="conn-row">
                  <button type="submit" className="btn btn-primary" disabled={hpcLoad || otp.length < 4}>
                    <Check size={16} aria-hidden="true" /> {hpcLoad ? "Checking…" : "Confirm"}
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => setOtp("")} disabled={hpcLoad}>Clear</button>
                </div>
              </form>
            ) : isActive ? (
              <div className="alert-box alert-success" style={{ margin: 0 }}>
                <CheckCircle2 size={18} aria-hidden="true" />
                <div>Everything that needs PARAKH works now: reading your class, the Activities, and sending cards. Use <b>Disconnect</b> when you are done for the day.</div>
              </div>
            ) : (
              <div className="conn-grid">
                <div className="conn-card">
                  <h3><Save size={15} aria-hidden="true" /> {role === "school" ? "The school's PARAKH login" : "Your PARAKH login"}</h3>
                  {hpcStatus?.has_credentials && (
                    <div className="conn-saved">
                      <CheckCircle2 size={15} aria-hidden="true" />
                      <span>Saved: <code>{hpcStatus.saved_hpc_login_id}</code></span>
                      <button type="button" className="portal-link-btn" onClick={() => { if (hpcStatus.saved_hpc_login_id) setLoginId(hpcStatus.saved_hpc_login_id); }}>
                        Use it
                      </button>
                    </div>
                  )}
                  <form onSubmit={onSaveCredentials} autoComplete="off" className="conn-form">
                    <div className="form-group">
                      <label className="form-label" htmlFor={`parakh_hpc_login_${role}`}>{role === "school" ? "School login ID or mobile" : "Staff code or login ID"}</label>
                      <input type="text" name={`parakh_hpc_login_${role}`} id={`parakh_hpc_login_${role}`} autoComplete="new-password" data-lpignore="true"
                             className="form-input" placeholder="e.g. BAA890 or 9876543210" value={loginId} onChange={(e) => setLoginId(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor={`parakh_hpc_password_${role}`}>PARAKH password</label>
                      <input type="password" name={`parakh_hpc_password_${role}`} id={`parakh_hpc_password_${role}`} autoComplete="new-password" data-lpignore="true"
                             className="form-input" placeholder={hpcStatus?.has_credentials ? "Saved - type a new one only to change it" : "Your PARAKH password"}
                             value={pwd} onChange={(e) => setPassword(e.target.value)} required />
                    </div>
                    <button type="submit" className="btn btn-outline" disabled={hpcLoad}><Save size={14} aria-hidden="true" /> Save login</button>
                  </form>
                </div>
                <div className="conn-card conn-go">
                  <span className="conn-lock"><Lock size={22} aria-hidden="true" /></span>
                  <h3>Connect to PARAKH</h3>
                  <p>PARAKH shows a small picture with a code. Type it in, and the app stays connected while you work.</p>
                  <button type="button" onClick={onStartSession} className="btn btn-primary btn-lg" disabled={hpcLoad}>
                    <PlayCircle size={18} aria-hidden="true" /> {hpcLoad ? "Opening PARAKH…" : "Connect"}
                  </button>
                  {hpcLoad && <small>Getting the captcha picture from PARAKH…</small>}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    );
  };

  // ─── Multi-Select Helpers ────────────────────────────────────────────────
  const renderStageChips = (stageStr?: string, stagesArr?: string[]) => {
    let list: string[] = [];
    if (stagesArr && stagesArr.length > 0) {
      list = stagesArr;
    } else if (stageStr) {
      list = stageStr.split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (list.length === 0) list = ["Preparatory"];

    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
        {list.map((stg) => {
          const match = ALL_STAGES.find((s) => s.id.toLowerCase() === stg.toLowerCase());
          const badgeClass = match ? match.badgeClass : "stage-chip-preparatory";
          return (
            <span key={stg} className={`stage-chip ${badgeClass}`}>
              {stg}
            </span>
          );
        })}
      </div>
    );
  };

  const toggleStage = (stgId: string) => {
    setNewTeacherStages((prev) => {
      const exists = prev.includes(stgId);
      const next = exists ? prev.filter((s) => s !== stgId) : [...prev, stgId];
      if (next.length === 0) return [stgId]; // Keep at least one
      // Auto-update grades
      const validGrades = ALL_STAGES.filter((s) => next.includes(s.id)).flatMap((s) => s.grades);
      setNewTeacherGrades((prevGrades) => {
        const kept = prevGrades.filter((g) => validGrades.includes(g));
        return kept.length > 0 ? kept : (validGrades.length > 0 ? [validGrades[0]] : ["Grade 3"]);
      });
      return next;
    });
  };

  const toggleGrade = (grade: string) => {
    setNewTeacherGrades((prev) => {
      const exists = prev.includes(grade);
      const next = exists ? prev.filter((g) => g !== grade) : [...prev, grade];
      return next.length > 0 ? next : [grade]; // Keep at least one
    });
  };

  // ─── Render ───────────────────────────────────────────────────────────────


  const statusAlert = statusMsg && (
    <div className={`alert-box alert-${statusMsg.type} app-alert`} role={statusMsg.type === "error" ? "alert" : "status"}>
      {statusMsg.type === "success" && <CheckCircle2 size={18} aria-hidden="true" />}
      {statusMsg.type === "error" && <AlertCircle size={18} aria-hidden="true" />}
      {statusMsg.type === "info" && <ShieldCheck size={18} aria-hidden="true" />}
      {statusMsg.type === "warning" && <AlertCircle size={18} aria-hidden="true" />}
      <div style={{ flex: 1 }}>{statusMsg.text}</div>
      <button type="button" className="alert-close" onClick={() => setStatusMsg(null)} aria-label="Close message"><X size={16} /></button>
    </div>
  );

  const logo = (
    <svg viewBox="0 0 40 40" width="34" height="34" aria-hidden="true">
      <rect x="2" y="2" width="36" height="36" rx="10" fill="var(--brand-500)" />
      <path d="M11 20.5l6 6 12-13" fill="none" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );

  // ─── Signed out: a calm split page ──────────────────────────────────────
  if (!user) {
    return (
      <div className="auth-page">
        <section className="auth-brand" aria-label="About Teacher Assist">
          <div className="auth-logo">{logo}<span>Teacher Assist</span></div>
          <div className="auth-pitch">
            <h1>Holistic Progress Cards, without the late nights.</h1>
            <p>Set up your class once, fill what is different for each student, and send every card to PARAKH in one go.</p>
            <ul className="auth-points">
              <li><CheckCircle2 size={18} aria-hidden="true" /> Activities and levels for the whole class in minutes</li>
              <li><CheckCircle2 size={18} aria-hidden="true" /> One clean Excel file per class, checked as you type</li>
              <li><CheckCircle2 size={18} aria-hidden="true" /> Every save to PARAKH backed up first</li>
            </ul>
          </div>
          <p className="auth-note">Independent tool. Not an official government service and not made by NCERT, PARAKH or the Ministry of Education.</p>
        </section>
        <section className="auth-panel">
          <div className="auth-card">
            <h2>{authTab === "register" ? "Register your school" : "Sign in"}</h2>
            <p className="auth-sub">{authTab === "register" ? "One account per school, with its 11-digit UDISE+ code." : "Welcome back. Choose who is signing in."}</p>
            {statusAlert}
            <div className="segmented" role="tablist" aria-label="Who is signing in">
              <button type="button" role="tab" aria-selected={authTab === "teacher_login"} className={authTab === "teacher_login" ? "active" : ""}
                      onClick={() => { setAuthTab("teacher_login"); setStatusMsg(null); }}><GraduationCap size={15} aria-hidden="true" /> Teacher</button>
              <button type="button" role="tab" aria-selected={authTab === "admin_login"} className={authTab === "admin_login" ? "active" : ""}
                      onClick={() => { setAuthTab("admin_login"); setStatusMsg(null); }}><Building2 size={15} aria-hidden="true" /> School admin</button>
              <button type="button" role="tab" aria-selected={authTab === "register"} className={authTab === "register" ? "active" : ""}
                      onClick={() => { setAuthTab("register"); setStatusMsg(null); }}><School size={15} aria-hidden="true" /> New school</button>
            </div>
              {authTab === "admin_login" && appAdminSetup && (
                <form onSubmit={handleAppAdminSetup}>
                  <p className="lib-muted">First sign-in of the application admin <b>{appAdminSetup}</b>. Choose its password (at least 12
                    characters). This works only in a browser on the server PC.</p>
                  <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                    <label className="form-label" htmlFor="app_admin_pw">New password</label>
                    <input id="app_admin_pw" type="password" className="form-input" minLength={12} autoComplete="new-password"
                           value={setupPassword} onChange={(e) => setSetupPassword(e.target.value)} required />
                  </div>
                  <div className="form-group" style={{ marginBottom: "1.5rem" }}>
                    <label className="form-label" htmlFor="app_admin_pw2">Type it again</label>
                    <input id="app_admin_pw2" type="password" className="form-input" autoComplete="new-password"
                           value={setupAgain} onChange={(e) => setSetupAgain(e.target.value)} required />
                  </div>
                  <button type="submit" className="btn btn-primary" style={{ width: "100%" }}
                          disabled={loading || setupPassword.length < 12 || setupPassword !== setupAgain}>
                    <KeyRound size={16} /> Set the password
                  </button>
                  <button type="button" className="portal-link-btn" onClick={() => setAppAdminSetup(null)}>Back to sign in</button>
                </form>
              )}
              {authTab === "admin_login" && !appAdminSetup && (
                <form onSubmit={(e) => handleLogin(e, "SCHOOL_ADMIN")}>
                  <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                    <label className="form-label"><span>UDISE+ Code or Admin Email</span><span className="form-hint">11-digit code (application admin: your login ID)</span></label>
                    <input type="text" className="form-input" placeholder="e.g. 27010100101 or principal@school.edu.in" value={adminIdentifier} onChange={(e) => setAdminIdentifier(e.target.value)} required />
                  </div>
                  <div className="form-group" style={{ marginBottom: "1.5rem" }}>
                    <label className="form-label">School Admin Password</label>
                    <input type="password" className="form-input" placeholder="••••••••••••" value={adminPassword} onChange={(e) => setAdminPassword(e.target.value)} required />
                  </div>
                  <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={loading}>
                    <KeyRound size={16} /> {loading ? "Authenticating..." : "Sign In as School Admin"}
                  </button>
                </form>
              )}

              {authTab === "teacher_login" && (
                <form onSubmit={(e) => handleLogin(e, "TEACHER")}>
                  <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                    <label className="form-label">Teacher Username</label>
                    <input type="text" className="form-input" placeholder="e.g. sunita_rao" value={teacherUsername} onChange={(e) => setTeacherUsername(e.target.value)} required />
                  </div>
                  <div className="form-group" style={{ marginBottom: "1.5rem" }}>
                    <label className="form-label">Teacher Password</label>
                    <input type="password" className="form-input" placeholder="••••••••••••" value={teacherPassword} onChange={(e) => setTeacherPassword(e.target.value)} required />
                  </div>
                  <button type="submit" className="btn btn-green" style={{ width: "100%" }} disabled={loading}>
                    <GraduationCap size={16} /> {loading ? "Signing In..." : "Sign In to Teacher Workspace"}
                  </button>
                </form>
              )}

              {authTab === "register" && (
                <form onSubmit={handleSchoolRegister}>
                  <div className="alert-box alert-info" style={{ marginBottom: "1.2rem", padding: "0.75rem 1rem" }}>
                    <ShieldCheck size={18} />
                    <div><b>Strict Unique Registration:</b> Each school registers exactly once under its 11-digit UDISE+ code.</div>
                  </div>
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label"><span>11-Digit UDISE+ Code *</span>{regUdise.length === 11 && <span style={{ color: "var(--green-500)", fontWeight: 700 }}>✓</span>}</label>
                      <input type="text" maxLength={11} className={`form-input ${regUdise.length === 11 ? "valid-udise" : ""}`} placeholder="e.g. 27010100101" value={regUdise} onChange={(e) => setRegUdise(e.target.value.replace(/\D/g, ""))} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">School name (as on UDISE) *</label>
                      <input type="text" className="form-input" placeholder="e.g. St. Xavier Public School" value={regSchoolName} onChange={(e) => setRegSchoolName(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">State *</label>
                      <input type="text" className="form-input" placeholder="e.g. Maharashtra" value={regState} onChange={(e) => setRegState(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">District *</label>
                      <input type="text" className="form-input" placeholder="e.g. Mumbai" value={regDistrict} onChange={(e) => setRegDistrict(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Block / Tehsil</label>
                      <input type="text" className="form-input" placeholder="e.g. Mumbai West" value={regBlock} onChange={(e) => setRegBlock(e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Principal / Admin Name *</label>
                      <input type="text" className="form-input" placeholder="e.g. Dr. Ramesh Kumar" value={regAdminName} onChange={(e) => setRegAdminName(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Admin Email *</label>
                      <input type="email" className="form-input" placeholder="principal@school.edu.in" value={regAdminEmail} onChange={(e) => setRegAdminEmail(e.target.value)} required />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Create Admin Password *</label>
                      <input type="password" className="form-input" placeholder="Min 8 characters" minLength={8} value={regPassword} onChange={(e) => setRegPassword(e.target.value)} required />
                    </div>
                  </div>
                  <button type="submit" className="btn btn-saffron" style={{ width: "100%" }} disabled={loading}>
                    <School size={16} /> {loading ? "Verifying & Registering..." : "Register School on PARAKH Hub"}
                  </button>
                </form>
              )}
          </div>
        </section>
      </div>
    );
  }

  // ─── The application admin: its own pages, above every school ─────────────
  if (user.role === "APP_ADMIN") {
    return <main className="content">{statusAlert}<PlatformAdmin api={cardsApi} onLogout={handleLogout} /></main>;
  }

  // ─── Signed in: sidebar + top bar ───────────────────────────────────────
  const isTeacher = user.role === "TEACHER";
  const onLibrary = location.pathname.startsWith("/activities");
  const parakh = isTeacher ? teacherHpcStatus : schoolHpcStatus;
  const initials = (user.name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const page = onLibrary ? PAGES.library : isTeacher ? PAGES[teacherTab] : PAGES[schoolTab === "teachers" ? "school_teachers" : "school_students"];
  const goTeacher = (tab: TeacherTab) => {
    if (tab === "roster") loadTeacherRoster(activeTeacherStage);
    if (tab === "activities") setGridFocus(undefined);
    setTeacherTab(tab);
    setNavOpen(false);
    if (onLibrary) navigate("/");
  };
  const goSchool = (tab: "teachers" | "students") => {
    if (tab === "students") loadSchoolRoster(schoolActiveStage);
    setSchoolTab(tab);
    setNavOpen(false);
    if (onLibrary) navigate("/");
  };
  const openParakh = () => {
    if (onLibrary) navigate("/");
    if (isTeacher) setShowTeacherHpcPanel(true); else setShowSchoolHpcPanel(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className={`shell ${navOpen ? "nav-open" : ""}`}>
      <aside className="sidebar" aria-label="Main">
        <div className="sb-brand">{logo}<div><b>Teacher Assist</b><span>HPC helper</span></div></div>
        <div className="sb-school">
          <span className="sb-school-name">{user.school_name || "Your school"}</span>
          <span className="sb-school-meta">{isTeacher ? `Class teacher${user.assigned_grade ? ` · ${user.assigned_grade}${user.assigned_section ? ` ${user.assigned_section}` : ""}` : ""}` : "School admin"}</span>
        </div>
        <nav className="sb-nav">
          {isTeacher ? (
            <>
              <div className="sb-section">Your HPC steps</div>
              {TEACHER_STEPS.map((step, i) => {
                const Icon = step.icon;
                const active = !onLibrary && teacherTab === step.id;
                return (
                  <button key={step.id} type="button" className={`sb-item ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}
                          onClick={() => goTeacher(step.id)}>
                    <span className="sb-step">{i + 1}</span>
                    <span className="sb-text"><b>{step.label}</b><small>{step.hint}</small></span>
                    <Icon size={16} className="sb-icon" aria-hidden="true" />
                  </button>
                );
              })}
            </>
          ) : (
            <>
              <div className="sb-section">School</div>
              <button type="button" className={`sb-item ${!onLibrary && schoolTab === "teachers" ? "active" : ""}`} onClick={() => goSchool("teachers")}>
                <Users size={17} className="sb-lead" aria-hidden="true" /><span className="sb-text"><b>Teachers</b><small>Accounts and classes</small></span>
              </button>
              <button type="button" className={`sb-item ${!onLibrary && schoolTab === "students" ? "active" : ""}`} onClick={() => goSchool("students")}>
                <GraduationCap size={17} className="sb-lead" aria-hidden="true" /><span className="sb-text"><b>Students</b><small>Every class at a glance</small></span>
              </button>
            </>
          )}
          <div className="sb-section">Resources</div>
          <NavLink to="/activities/preparatory" onClick={() => setNavOpen(false)} className={({ isActive }) => `sb-item ${isActive ? "active" : ""}`}>
            <BookOpen size={17} className="sb-lead" aria-hidden="true" /><span className="sb-text"><b>Activity Library</b><small>{isTeacher ? "Edit or add activities" : "Activities from PARAKH"}</small></span>
          </NavLink>
        </nav>
        <div className="sb-foot">
          <div className="sb-user"><span className="sb-avatar" aria-hidden="true">{initials}</span><div><b>{user.name}</b><small>{isTeacher ? "Teacher" : "School admin"}</small></div></div>
          <button type="button" className="sb-logout" onClick={handleLogout}><LogOut size={15} aria-hidden="true" /> Sign out</button>
        </div>
      </aside>
      {navOpen && <button type="button" className="sb-scrim" aria-label="Close menu" onClick={() => setNavOpen(false)} />}

      <div className="shell-main">
        <header className="topbar">
          <button type="button" className="tb-menu" aria-label="Open menu" onClick={() => setNavOpen(true)}><Menu size={20} /></button>
          <div className="tb-titles">
            <h1>{page.title}</h1>
            <p>{page.desc}</p>
          </div>
          <button type="button" className={`parakh-pill ${parakh?.logged_in ? "on" : "off"}`} onClick={openParakh}
                  aria-label={parakh?.logged_in ? "PARAKH connected - show connection" : "Not connected to PARAKH - connect"}>
            <span className="dot" aria-hidden="true" />
            <span>{parakh?.logged_in ? "PARAKH connected" : "PARAKH not connected"}</span>
            {!parakh?.logged_in && <span className="pill-cta">Connect</span>}
          </button>
        </header>

        <main className="content">
          {statusAlert}
        {/* ── SCHOOL ADMIN DASHBOARD ────────────────────────────────────── */}
        <Routes>
          <Route path="/activities/:stage?" element={user ? <ActivityLibraryPage api={cardsApi} isAdmin={user.role === "SCHOOL_ADMIN"} /> : null} />
          <Route path="*" element={<>
        {user?.role === "SCHOOL_ADMIN" && (
          <div>
            {/* School HPC Session Panel */}
            {showSchoolHpcPanel && <HpcSessionPanel
              role="school"
              hpcStatus={schoolHpcStatus}
              loading={schoolHpcLoading}
              loginId={schoolHpcLoginId} setLoginId={setSchoolHpcLoginId}
              password={schoolHpcPassword} setPassword={setSchoolHpcPassword}
              otpStep={schoolHpcOtpStep}
              otp={schoolHpcOtp} setOtp={setSchoolHpcOtp}
              onSaveCredentials={handleSaveSchoolHpcCredentials}
              onStartSession={handleStartSchoolSession}
              onVerifyOtp={handleVerifySchoolOtp}
              onEndSession={handleEndSchoolSession}
              onRefreshStatus={fetchSchoolHpcStatus}
              showPanel={showSchoolHpcPanel}
              setShowPanel={setShowSchoolHpcPanel}
            />}
            {schoolCaptcha && (
              <CaptchaStep who="school" image={schoolCaptcha} onDone={(r) => afterCaptcha("school", r)} onCancel={() => setSchoolCaptcha(null)} />
            )}

            {/* KPIs */}
            {schoolStats && (
              <div className="kpi-grid">
                <div className="kpi-card saffron">
                  <div className="kpi-top"><span className="kpi-label">Classroom Teachers</span><div className="kpi-icon saffron"><Users size={20} /></div></div>
                  <div className="kpi-number">{schoolStats.total_teachers}</div>
                  <div className="kpi-subtext">Provisioned educator accounts</div>
                </div>
                <div className="kpi-card navy">
                  <div className="kpi-top"><span className="kpi-label">Uploaded Students</span><div className="kpi-icon navy"><GraduationCap size={20} /></div></div>
                  <div className="kpi-number">{schoolStats.total_students}</div>
                  <div className="kpi-subtext">Across Preparatory &amp; Middle</div>
                </div>
                <div className="kpi-card green">
                  <div className="kpi-top"><span className="kpi-label">Verified &amp; Submitted</span><div className="kpi-icon green"><CheckCircle2 size={20} /></div></div>
                  <div className="kpi-number" style={{ color: "var(--green-500)" }}>{schoolStats.submitted_and_verified}</div>
                  <div className="kpi-subtext">Progress cards on PARAKH</div>
                </div>
                <div className="kpi-card purple">
                  <div className="kpi-top"><span className="kpi-label">Completion Rate</span><div className="kpi-icon purple"><FileCheck2 size={20} /></div></div>
                  <div className="kpi-number">{schoolStats.completion_rate_percent}%</div>
                  <div className="kpi-subtext">School-wide compliance target</div>
                </div>
              </div>
            )}

            {/* Tab 1: Teachers Table */}
            {schoolTab === "teachers" && (
            <div className="ui-panel">
              <div className="panel-header">
                <div className="panel-title"><Users size={20} color="#CF4A0A" /><span>Teachers</span></div>
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <button onClick={fetchSchoolData} className="btn btn-outline" style={{ padding: "0.5rem 0.85rem" }}>
                    <RefreshCw size={15} /> Refresh
                  </button>
                  <button onClick={() => setShowAddTeacherModal(true)} className="btn btn-primary">
                    <Plus size={16} /> Add Class Teacher
                  </button>
                </div>
              </div>

              {teachers.length === 0 ? (
                <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--text-muted)" }}>
                  <GraduationCap size={40} style={{ margin: "0 auto 0.75rem", opacity: 0.4 }} />
                  <p style={{ fontWeight: 600 }}>No teachers added yet.</p>
                  <p style={{ fontSize: "0.85rem" }}>Click "+ Add Class Teacher" to assign teachers to Grade 3-8 sections.</p>
                </div>
              ) : (
                <div className="data-table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Teacher Name</th>
                        <th>User ID (Username)</th>
                        <th>Assigned Stage(s)</th>
                        <th>Class &amp; Section</th>
                        <th>HPC Session</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {teachers.map((t) => (
                        <tr key={t.id}>
                          <td>
                            <b>{t.teacher_name}</b>
                            {t.employee_code && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Code: {t.employee_code}</div>}
                          </td>
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                              <code style={{ fontSize: "0.82rem", background: "#F1F5F9", padding: "0.2rem 0.45rem", borderRadius: "4px", fontWeight: 700 }}>
                                {t.username}
                              </code>
                              <button
                                type="button"
                                onClick={() => copyToClipboard(t.username, "Username")}
                                title="Copy Username / User ID"
                                style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex", padding: 2 }}
                              >
                                <Copy size={13} />
                              </button>
                            </div>
                          </td>
                          <td>
                            {renderStageChips(t.assigned_stage, t.assigned_stages)}
                          </td>
                          <td><b>{t.assigned_grade}</b> · Sec {t.assigned_section}</td>
                          <td>
                            {t.parakh_connected
                              ? <span className="status-pill active">🟢 Active ({t.parakh_user || "HPC"})</span>
                              : <span className="status-pill inactive">{t.has_hpc_credentials ? "🟡 Credentials Saved" : "🔴 Not Connected"}</span>}
                          </td>
                          <td>
                            {deletingTeacherId === t.id ? (
                              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                <span style={{ fontSize: "0.78rem", color: "var(--danger-600)", fontWeight: 700 }}>Switch off?</span>
                                <button
                                  onClick={() => confirmDeleteTeacher(t.id)}
                                  className="btn btn-outline"
                                  style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", background: "#FEE2E2", color: "#DC2626", borderColor: "#FCA5A5" }}
                                >
                                  Yes
                                </button>
                                <button
                                  onClick={() => setDeletingTeacherId(null)}
                                  className="btn btn-outline"
                                  style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <div style={{ display: "flex", gap: "0.4rem" }}>
                                <button
                                  onClick={() => openEditModal(t)}
                                  className="btn btn-outline"
                                  style={{ padding: "0.3rem 0.6rem", color: "var(--chakra-navy)", borderColor: "var(--border-medium)" }}
                                  title="Edit Teacher Account (Stages, Classes, Password)"
                                >
                                  <Edit size={14} /> Edit
                                </button>
                                <button
                                  onClick={() => setDeletingTeacherId(t.id)}
                                  className="btn btn-outline"
                                  style={{ padding: "0.3rem 0.6rem", color: "var(--danger-500)", borderColor: "#FCA5A5" }}
                                  title="Switch off this teacher (their upload history is kept)"
                                  aria-label={`Switch off ${t.teacher_name}`}
                                >
                                  <UserX size={14} />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                </div>
              )}
            </div>
            )}

            {/* Tab 2: Synced Students Directory (School Admin) */}
            {schoolTab === "students" && (
              <div className="ui-panel">
                <div className="panel-header">
                  <div className="panel-title">
                    <GraduationCap size={20} color="#CF4A0A" />
                    <span>School Students Directory (PARAKH Synced)</span>
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                    {schoolRosterLastSynced && (
                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginRight: "0.3rem" }}>
                        🕒 Synced: <b>{schoolRosterLastSynced}</b>
                      </span>
                    )}
                    {schoolHpcStatus?.logged_in && (
                      <button
                        onClick={handleSyncSchoolRoster}
                        className="btn btn-green"
                        disabled={schoolStudentsLoading}
                        style={{ padding: "0.45rem 0.85rem", fontSize: "0.84rem" }}
                        title="Fetch latest student roster directly from PARAKH portal"
                      >
                        <RefreshCw size={14} className={schoolStudentsLoading ? "spin" : ""} /> Sync from Portal
                      </button>
                    )}
                    <button
                      onClick={() => loadSchoolRoster(schoolActiveStage)}
                      className="btn btn-outline"
                      disabled={schoolStudentsLoading}
                      style={{ padding: "0.45rem 0.85rem", fontSize: "0.84rem" }}
                      title="Reload cached roster for this stage"
                    >
                      <RefreshCw size={14} className={schoolStudentsLoading ? "spin" : ""} /> Refresh Cache
                    </button>
                  </div>
                </div>

                {/* Stage switcher bar */}
                <div className="stage-switch-bar">
                  <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--chakra-navy)", marginLeft: "0.4rem", marginRight: "0.3rem" }}>
                    Select Stage:
                  </span>
                  {["Foundational", "Preparatory", "Middle"].map((stg) => (
                    <button
                      key={stg}
                      type="button"
                      className={`stage-switch-btn ${schoolActiveStage === stg ? "active" : ""}`}
                      onClick={() => {
                        setSchoolActiveStage(stg);
                        loadSchoolRoster(stg);
                      }}
                    >
                      {stg} Stage
                    </button>
                  ))}
                </div>

                {/* Search input */}
                <div className="roster-controls-bar">
                  <div className="roster-search-input">
                    <Search size={16} color="var(--text-light)" />
                    <input
                      type="text"
                      placeholder="Search student name, APAAR ID, or admission no..."
                      value={schoolStudentSearch}
                      onChange={(e) => setSchoolStudentSearch(e.target.value)}
                    />
                  </div>
                  {schoolStudents.length > 0 && (
                    <span className="gov-pill">
                      Total {schoolActiveStage} Students: <b>{schoolStudents.length}</b>
                    </span>
                  )}
                </div>

                {(() => {
                  if (schoolStudentsLoading && schoolStudents.length === 0) {
                    return (
                      <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-muted)" }}>
                        <RefreshCw size={36} className="spin" style={{ margin: "0 auto 1rem", color: "var(--chakra-blue)" }} />
                        <div style={{ fontWeight: 700 }}>Loading {schoolActiveStage} students...</div>
                      </div>
                    );
                  }

                  if (schoolStudents.length === 0) {
                    return (
                      <div className="empty-roster-box">
                        <GraduationCap size={48} color="#CF4A0A" style={{ margin: "0 auto 1rem", opacity: 0.5 }} />
                        <h3 style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--chakra-navy)" }}>
                          No Students Synced for {schoolActiveStage} Stage Yet
                        </h3>
                        <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", maxWidth: 500, margin: "0.5rem auto 1rem" }}>
                          Students are synced automatically when assigned teachers log in and fetch rosters for their classes from PARAKH.
                        </p>
                      </div>
                    );
                  }

                  const query = schoolStudentSearch.trim().toLowerCase();
                  const filtered = schoolStudents.filter((s) => {
                    if (!query) return true;
                    return (
                      (s.student_name || "").toLowerCase().includes(query) ||
                      (s.admission_number || "").toLowerCase().includes(query) ||
                      (s.apaar_id || "").toLowerCase().includes(query)
                    );
                  });

                  return (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th style={{ width: 45 }}>#</th>
                            <th>Student Name</th>
                            <th>Admission / Reg ID</th>
                            <th>APAAR ID</th>
                            <th>Grade &amp; Section</th>
                            <th>Gender</th>
                            <th>PARAKH Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((s, idx) => {
                            const rawStatus = (s.status || "PENDING").toUpperCase();
                            const isDone = rawStatus === "COMPLETED" || rawStatus === "SUCCESS";
                            const isProg = rawStatus === "IN_PROGRESS";
                            const statusCls = isDone ? "completed" : (isProg ? "in-progress" : "pending");
                            const { label: genderLabel, cls: avatarCls } = genderInfo(s.gender);
                            const initials = (s.student_name || "S").split(" ").map((n) => n[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();

                            return (
                              <tr key={s.student_id || idx}>
                                <td style={{ color: "var(--text-light)", fontWeight: 600 }}>{idx + 1}</td>
                                <td>
                                  <div className="student-name-cell">
                                    <div className={`student-avatar ${avatarCls}`}>{initials}</div>
                                    <div>
                                      <div style={{ fontWeight: 700, color: "var(--chakra-navy)" }}>{s.student_name}</div>
                                      <div style={{ fontSize: "0.74rem", color: "var(--text-light)" }}>
                                        Mother Tongue: {s.mother_tongue || "Kashmiri"}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td><span className="mono-chip">{s.admission_number || s.hpc_login_id || "—"}</span></td>
                                <td>
                                  {s.apaar_id ? (
                                    <span className="mono-chip" style={{ color: "var(--brand-600)", fontWeight: 600 }}>
                                      {s.apaar_id}
                                    </span>
                                  ) : (
                                    <span style={{ color: "var(--text-light)", fontSize: "0.8rem" }}>—</span>
                                  )}
                                </td>
                                <td>
                                  <b>{s.grade}</b>
                                  <span style={{ color: "var(--text-muted)", marginLeft: "0.3rem" }}>Sec {s.section || "A"}</span>
                                </td>
                                <td>
                                  <span style={{ fontSize: "0.84rem", fontWeight: 600, color: avatarCls === "female" ? "#9D174D" : avatarCls === "male" ? "#3730A3" : "var(--text-muted)" }}>
                                    {genderLabel}
                                  </span>
                                </td>
                                <td>
                                  <span className={`status-tag ${statusCls}`}>
                                    {isDone && <CheckCircle2 size={12} />}
                                    {isProg && <Clock size={12} />}
                                    {rawStatus.replace("_", " ")}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Add Teacher Modal */}
            {showAddTeacherModal && (
              <div className="modal-overlay">
                <div className="modal-dialog" style={{ maxWidth: 640 }}>
                  <div className="modal-header">
                    <div className="modal-title">Provision New Class Teacher (Multi-Stage Role)</div>
                    <button onClick={() => setShowAddTeacherModal(false)} style={{ background: "transparent", border: "none", fontSize: "1.2rem", cursor: "pointer" }}>✕</button>
                  </div>
                  <form onSubmit={handleCreateTeacher}>
                    <div className="modal-body">
                      <div className="form-group" style={{ marginBottom: "1rem" }}>
                        <label className="form-label">Full Teacher Name *</label>
                        <input type="text" className="form-input" placeholder="e.g. Mrs. Sunita Rao" value={newTeacherName} onChange={(e) => setNewTeacherName(e.target.value)} required />
                      </div>
                      <div className="form-group" style={{ marginBottom: "1rem" }}>
                        <label className="form-label">Unique Login Username *</label>
                        <input type="text" className="form-input" placeholder="e.g. sunita_rao" value={newTeacherUsername} onChange={(e) => setNewTeacherUsername(e.target.value.toLowerCase().replace(/\s/g, "_"))} required />
                      </div>
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <label className="form-label">Initial Password *</label>
                        <input type="password" className="form-input" placeholder="Min 8 characters" minLength={8} value={newTeacherPassword} onChange={(e) => setNewTeacherPassword(e.target.value)} required />
                      </div>

                      {/* Multi-Selective HPC Stages */}
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                          <label className="form-label" style={{ margin: 0 }}>
                            Assigned HPC Stage(s) * <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>(Multi-Selective)</span>
                          </label>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button
                              type="button"
                              onClick={() => {
                                const allIds = ALL_STAGES.map((s) => s.id);
                                setNewTeacherStages(allIds);
                                setNewTeacherGrades(ALL_STAGES.flatMap((s) => s.grades));
                              }}
                              className="btn btn-outline"
                              style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                            >
                              Select All Stages
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setNewTeacherStages(["Preparatory"]);
                                setNewTeacherGrades(["Grade 3"]);
                              }}
                              className="btn btn-outline"
                              style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                            >
                              Reset
                            </button>
                          </div>
                        </div>

                        <div className="multi-stage-grid">
                          {ALL_STAGES.map((stg) => {
                            const isSelected = newTeacherStages.includes(stg.id);
                            return (
                              <div
                                key={stg.id}
                                className={`stage-select-card ${isSelected ? "selected" : ""}`}
                                onClick={() => toggleStage(stg.id)}
                              >
                                <div style={{ marginTop: "2px" }}>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    readOnly
                                    style={{ cursor: "pointer", width: 16, height: 16, accentColor: "var(--chakra-blue)" }}
                                  />
                                </div>
                                <div>
                                  <div className="stage-card-title">{stg.label}</div>
                                  <div className="stage-card-desc">{stg.desc}</div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Multi-Selective Classes / Grades */}
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
                          <label className="form-label" style={{ margin: 0 }}>
                            Assigned Class(es) / Grade(s) * <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>(Click to toggle)</span>
                          </label>
                          <button
                            type="button"
                            onClick={() => {
                              const avail = ALL_STAGES.filter((s) => newTeacherStages.includes(s.id)).flatMap((s) => s.grades);
                              setNewTeacherGrades(avail);
                            }}
                            className="btn btn-outline"
                            style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                          >
                            Select All In Stages
                          </button>
                        </div>

                        <div className="grade-pills-wrap">
                          {ALL_STAGES.filter((s) => newTeacherStages.includes(s.id)).flatMap((s) => s.grades).map((grade) => {
                            const isSelected = newTeacherGrades.includes(grade);
                            return (
                              <div
                                key={grade}
                                className={`grade-pill-item ${isSelected ? "active" : ""}`}
                                onClick={() => toggleGrade(grade)}
                              >
                                {isSelected ? <Check size={13} /> : null}
                                <span>{grade}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Section */}
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label">Assigned Section(s) *</label>
                        <select className="form-select" value={newTeacherSection} onChange={(e) => setNewTeacherSection(e.target.value)}>
                          <option value="A">Section A</option>
                          <option value="B">Section B</option>
                          <option value="C">Section C</option>
                          <option value="D">Section D</option>
                          <option value="A, B">Sections A &amp; B</option>
                          <option value="All Sections">All Sections</option>
                        </select>
                      </div>
                    </div>
                    <div className="modal-footer">
                      <button type="button" onClick={() => setShowAddTeacherModal(false)} className="btn btn-outline">Cancel</button>
                      <button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Creating..." : "Save & Assign Multi-Stage Teacher"}</button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* Edit Teacher Modal */}
            {editingTeacher && (
              <div className="modal-overlay">
                <div className="modal-dialog" style={{ maxWidth: 640 }}>
                  <div className="modal-header">
                    <div className="modal-title">Edit Class Teacher: {editingTeacher.teacher_name}</div>
                    <button onClick={() => setEditingTeacher(null)} style={{ background: "transparent", border: "none", fontSize: "1.2rem", cursor: "pointer" }}>✕</button>
                  </div>
                  <form onSubmit={handleUpdateTeacher}>
                    <div className="modal-body">
                      <div className="form-group" style={{ marginBottom: "1rem" }}>
                        <label className="form-label">Full Teacher Name *</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editTeacherName}
                          onChange={(e) => setEditTeacherName(e.target.value)}
                          required
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: "1rem" }}>
                        <label className="form-label">Login Username / User ID *</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editTeacherUsername}
                          onChange={(e) => setEditTeacherUsername(e.target.value.toLowerCase().replace(/\s/g, "_"))}
                          required
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <label className="form-label">
                          Password <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>(Update or leave as current)</span>
                        </label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="Enter new password (min 8 characters) or leave unchanged"
                          value={editTeacherPassword}
                          onChange={(e) => setEditTeacherPassword(e.target.value)}
                        />
                      </div>

                      {/* Multi-Selective HPC Stages */}
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                          <label className="form-label" style={{ margin: 0 }}>
                            Assigned HPC Stage(s) * <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>(Multi-Selective)</span>
                          </label>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button
                              type="button"
                              onClick={() => {
                                const allIds = ALL_STAGES.map((s) => s.id);
                                setEditTeacherStages(allIds);
                                setEditTeacherGrades(ALL_STAGES.flatMap((s) => s.grades));
                              }}
                              className="btn btn-outline"
                              style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                            >
                              Select All
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditTeacherStages(["Preparatory"]);
                                setEditTeacherGrades(["Grade 3"]);
                              }}
                              className="btn btn-outline"
                              style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                            >
                              Reset
                            </button>
                          </div>
                        </div>

                        <div className="multi-stage-grid">
                          {ALL_STAGES.map((stg) => {
                            const isSelected = editTeacherStages.includes(stg.id);
                            return (
                              <div
                                key={stg.id}
                                className={`stage-select-card ${isSelected ? "selected" : ""}`}
                                onClick={() => toggleEditStage(stg.id)}
                              >
                                <div style={{ marginTop: "2px" }}>
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    readOnly
                                    style={{ cursor: "pointer", width: 16, height: 16, accentColor: "var(--chakra-blue)" }}
                                  />
                                </div>
                                <div>
                                  <div className="stage-card-title">{stg.label}</div>
                                  <div className="stage-card-desc">{stg.desc}</div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Multi-Selective Classes / Grades */}
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
                          <label className="form-label" style={{ margin: 0 }}>
                            Assigned Class(es) / Grade(s) * <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>(Click to toggle)</span>
                          </label>
                          <button
                            type="button"
                            onClick={() => {
                              const avail = ALL_STAGES.filter((s) => editTeacherStages.includes(s.id)).flatMap((s) => s.grades);
                              setEditTeacherGrades(avail);
                            }}
                            className="btn btn-outline"
                            style={{ padding: "0.2rem 0.5rem", fontSize: "0.74rem" }}
                          >
                            Select All In Stages
                          </button>
                        </div>

                        <div className="grade-pills-wrap">
                          {ALL_STAGES.filter((s) => editTeacherStages.includes(s.id)).flatMap((s) => s.grades).map((grade) => {
                            const isSelected = editTeacherGrades.includes(grade);
                            return (
                              <div
                                key={grade}
                                className={`grade-pill-item ${isSelected ? "active" : ""}`}
                                onClick={() => toggleEditGrade(grade)}
                              >
                                {isSelected ? <Check size={13} /> : null}
                                <span>{grade}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Section */}
                      <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                        <label className="form-label">Assigned Section(s) *</label>
                        <select
                          className="form-select"
                          value={editTeacherSection}
                          onChange={(e) => setEditTeacherSection(e.target.value)}
                        >
                          <option value="A">Section A</option>
                          <option value="B">Section B</option>
                          <option value="C">Section C</option>
                          <option value="D">Section D</option>
                          <option value="A, B">Sections A &amp; B</option>
                          <option value="All Sections">All Sections</option>
                        </select>
                      </div>

                      {/* Active Status */}
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.9rem" }}>
                          <input
                            type="checkbox"
                            checked={editTeacherActive}
                            onChange={(e) => setEditTeacherActive(e.target.checked)}
                            style={{ width: 16, height: 16, accentColor: "var(--chakra-blue)" }}
                          />
                          <span><b>Active Account</b> (Teacher can log in and manage evaluations)</span>
                        </label>
                      </div>
                    </div>
                    <div className="modal-footer">
                      <button type="button" onClick={() => setEditingTeacher(null)} className="btn btn-outline">Cancel</button>
                      <button type="submit" className="btn btn-primary" disabled={loading}>
                        {loading ? "Saving..." : "Save Changes"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

          </div>
        )}

        {/* ── TEACHER WORKSPACE ─────────────────────────────────────────── */}
        {user?.role === "TEACHER" && (
          <div>
            {/* Teacher HPC Session Panel */}
            {showTeacherHpcPanel && <HpcSessionPanel
              role="teacher"
              hpcStatus={teacherHpcStatus}
              loading={teacherHpcLoading}
              loginId={teacherHpcLoginId} setLoginId={setTeacherHpcLoginId}
              password={teacherHpcPassword} setPassword={setTeacherHpcPassword}
              otpStep={teacherHpcOtpStep}
              otp={teacherHpcOtp} setOtp={setTeacherHpcOtp}
              onSaveCredentials={handleSaveTeacherHpcCredentials}
              onStartSession={handleStartTeacherSession}
              onVerifyOtp={handleVerifyTeacherOtp}
              onEndSession={handleEndTeacherSession}
              onRefreshStatus={fetchTeacherHpcStatus}
              showPanel={showTeacherHpcPanel}
              setShowPanel={setShowTeacherHpcPanel}
            />}
            {teacherCaptcha && (
              <CaptchaStep who="teacher" image={teacherCaptcha} onDone={(r) => afterCaptcha("teacher", r)} onCancel={() => setTeacherCaptcha(null)} />
            )}

            {/* Tab 4: class settings for the Excel template (medium, working days, max marks, declaration) */}
            {teacherTab === "settings" && (
              <>
                {renderTeacherStageSwitcher()}
                <ClassSettings key={activeTeacherStage} api={cardsApi} stage={activeTeacherStage} />
              </>
            )}

            {/* Tab 2: Part B activities and levels per subject */}
            {teacherTab === "activities" && (
              <>
                {renderTeacherStageSwitcher()}
                <ActivitiesGrid key={activeTeacherStage} api={cardsApi} stage={activeTeacherStage} focusStudent={gridFocus}
                                libraryHref={`/activities/${activeTeacherStage.toLowerCase()}`}
                                uploadedFile={validationReport?.warnings?.some((w) => w.message.includes("old Activity columns"))
                                  ? uploadedFileName : undefined} />
              </>
            )}

            {/* Tab 3: class-wide answers (mother tongue and the like), one field for many students */}
            {teacherTab === "bulk" && (
              <>
                {renderTeacherStageSwitcher()}
                <LevelsGrid key={`levels-${activeTeacherStage}`} api={cardsApi} stage={activeTeacherStage} />
                <HpcBulkEntry api={cardsApi} stage={activeTeacherStage} />
              </>
            )}

            {/* Tab 5: download the class template, then upload the filled file */}
            {teacherTab === "upload" && teacherStagesList().length > 1 && (
              <AllStagesDownload api={cardsApi} stages={teacherStagesList()}
                                 onOpenSettings={(st) => { setActiveTeacherStage(st); setTeacherTab("settings"); }} />
            )}
            {teacherTab === "upload" && teacherStagesList().length > 1 && (
              <h3 className="section-label">Or one stage at a time</h3>
            )}
            {teacherTab === "upload" && renderTeacherStageSwitcher()}
            {teacherTab === "upload" && (
              <div className="ui-panel">
                <TemplatePanel key={activeTeacherStage} api={cardsApi} stage={activeTeacherStage} total={students.length}
                               onOpenSettings={() => setTeacherTab("settings")}
                               onFix={(id, where, name) => {
                                 if (where === "card") { setOpenCard({ id, name }); return; }
                                 setGridFocus(id);
                                 setTeacherTab("activities");
                               }} />
              </div>
            )}
            {teacherTab === "upload" && (
              <div className="ui-panel">
                {activeJobId && <UploadLive api={cardsApi} jobId={activeJobId} onFinished={afterUpload}
                                            onRetry={(id) => { setStatusMsg(null); setIsSubmitting(true); setActiveJobId(id); }} />}
                <div className="panel-header">
                  <div className="panel-title"><Upload size={20} color="#FF671F" /><span>Upload the filled Excel file</span></div>
                </div>

                <label className="dropzone" style={{ display: "block", marginBottom: "1.5rem" }}>
                  <input type="file" accept=".xlsx" onChange={handleFileUpload} style={{ display: "none" }} />
                  <FileSpreadsheet size={42} color="#CF4A0A" style={{ margin: "0 auto 0.8rem" }} />
                  <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "var(--chakra-navy)" }}>
                    {uploadedFileName ? `Selected: ${uploadedFileName}` : "Choose the filled Excel file (.xlsx)"}
                  </div>
                  <div style={{ fontSize: "0.82rem", color: "var(--text-light)", marginTop: "0.25rem" }}>
                    Every student is checked first. Nothing is sent to PARAKH until you press Sync.
                  </div>
                </label>

                {validationReport && (
                  <div style={{ marginTop: "1.5rem" }}>
                    {/* Validation result banner */}
                    <div style={{ padding: "1rem 1.4rem", borderRadius: "12px", background: validationReport.is_valid ? "var(--green-50)" : "var(--danger-100)", border: `1px solid ${validationReport.is_valid ? "var(--green-500)" : "var(--danger-500)"}`, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem", marginBottom: "1rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        {validationReport.is_valid ? <CheckCircle2 size={24} color="#046A38" /> : <AlertCircle size={24} color="#DC2626" />}
                        <div>
                          <div style={{ fontWeight: 800, fontSize: "1.05rem", color: validationReport.is_valid ? "#065F46" : "#991B1B" }}>
                            {validationReport.is_valid ? `✅ ${validationReport.total_records} student(s) ready to sync` : `❌ No student is ready yet · ${validationReport.error_count} issue(s)`}
                          </div>
                          <div style={{ fontSize: "0.82rem", color: validationReport.is_valid ? "#047857" : "#B91C1C" }}>
                            Stage: <b>{validationReport.detected_stage}</b>
                            {validationReport.is_valid && validationReport.error_count > 0 && <span style={{ color: "#B45309", marginLeft: "0.5rem" }}>· students with issues below will be skipped</span>}
                            {validationReport.warning_count > 0 && <span style={{ color: "#B45309", marginLeft: "0.5rem" }}>· {validationReport.warning_count} warning(s)</span>}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                        {/* Re-upload button — always visible so teacher is never stuck */}
                        <label
                          htmlFor="reupload-input"
                          className="btn btn-outline"
                          style={{ padding: "0.55rem 1rem", fontSize: "0.85rem", cursor: "pointer" }}
                          title="Pick a different or corrected Excel file"
                        >
                          <Upload size={14} /> Re-upload File
                          <input
                            id="reupload-input"
                            type="file"
                            accept=".xlsx"
                            style={{ display: "none" }}
                            onChange={(e) => {
                              setValidationReport(null);
                              setUploadedFileName("");
                              handleFileUpload(e);
                            }}
                          />
                        </label>
                        {/* Worker Speed Selector & Submit button */}
                        {(validationReport.is_valid || validationReport.error_count === 0) && (
                          <button
                            onClick={handleStartSubmission}
                            className="btn btn-green"
                            disabled={isSubmitting}
                            style={{ padding: "0.55rem 1.4rem" }}
                          >
                            <Sparkles size={16} /> {isSubmitting ? "Syncing..." : `Sync ${validationReport.total_records} student(s) to PARAKH`}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Error table */}
                    {validationReport.errors?.length > 0 && (
                      <div className="data-table-wrapper">
                        <div style={{ padding: "0.6rem 1rem", background: "#FEF2F2", borderBottom: "1px solid #FECACA", fontSize: "0.82rem", fontWeight: 600, color: "#991B1B" }}>
                          Fix these {validationReport.error_count} error(s) in the Excel file, then re-upload:
                        </div>
                        <table className="data-table">
                          <thead><tr><th>Excel Row</th><th>Field</th><th>Validation Issue</th></tr></thead>
                          <tbody>
                            {validationReport.errors.map((err: { row: number; field: string; message: string }, idx: number) => (
                              <tr key={idx}>
                                <td><b>Row {err.row}</b></td>
                                <td><code>{err.field}</code></td>
                                <td style={{ color: "var(--danger-500)" }}>{err.message}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: Roster */}
            {teacherTab === "roster" && (
              <div className="ui-panel">
                <div className="panel-header">
                  <div className="panel-title">
                    <FileSpreadsheet size={20} color="#046A38" />
                    <span>Your class</span>
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem" }}>
                    <button
                      onClick={() => handleSyncRoster(activeTeacherStage)}
                      className="btn btn-primary"
                      disabled={loading || fetchJob?.status === "RUNNING"}
                      style={{ padding: "0.45rem 0.9rem", fontSize: "0.84rem" }}
                    >
                      <RefreshCw size={15} className={fetchJob?.status === "RUNNING" ? "spin" : ""} />
                      {fetchJob?.status === "RUNNING" ? "Fetching…" : "Fetch from PARAKH"}
                    </button>
                    <button
                      onClick={() => handleDownloadExcel(activeTeacherStage)}
                      className="btn btn-saffron"
                      disabled={loading}
                      style={{ padding: "0.45rem 0.9rem", fontSize: "0.84rem" }}
                    >
                      <Download size={15} /> Download Excel
                    </button>
                  </div>
                </div>

                {/* Session connection notice */}
                {teacherHpcStatus?.logged_in ? (
                  <div style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", borderRadius: "10px", marginBottom: "1rem", overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.65rem 1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <ShieldCheck size={18} color="#046A38" />
                        <div style={{ fontSize: "0.86rem" }}>
                          <b style={{ color: "#065F46" }}>PARAKH Session Active:</b>{" "}
                          <span style={{ color: "#047857" }}>{teacherHpcStatus.user || "Staff"} · {teacherHpcStatus.school || user.school_name}</span>
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
                        {/* 🔄 Refresh Session Button */}
                        <button
                          id="btn-refresh-parakh-session"
                          onClick={handleRefreshTeacherSession}
                          disabled={teacherHpcRefreshing}
                          style={{
                            display: "flex", alignItems: "center", gap: "0.35rem",
                            padding: "0.32rem 0.75rem", fontSize: "0.8rem", fontWeight: 600,
                            borderRadius: "6px", border: "1px solid #059669",
                            background: teacherHpcRefreshing ? "#D1FAE5" : "#FFFFFF",
                            color: "#065F46", cursor: teacherHpcRefreshing ? "not-allowed" : "pointer",
                            transition: "all 0.2s",
                          }}
                          title="Reconnect to PARAKH (you will type a captcha)"
                        >
                          <RefreshCw size={13} style={{ animation: teacherHpcRefreshing ? "spin 1s linear infinite" : "none" }} />
                          {teacherHpcRefreshing ? "Reconnecting…" : "Reconnect"}
                        </button>
                        <button onClick={() => setShowTeacherHpcPanel(!showTeacherHpcPanel)} className="portal-link-btn">
                          {showTeacherHpcPanel ? "Hide Details" : "Session Details"}
                        </button>
                      </div>
                    </div>
                    {/* Collapsible refresh log */}
                    {showTeacherRefreshLog && teacherHpcRefreshLog && (
                      <div style={{ borderTop: "1px solid #A7F3D0", background: "#F0FDF4", padding: "0.75rem 1rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                          <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#065F46" }}>🖥️ Refresh Log (refresh_session.py output)</span>
                          <button
                            onClick={() => setShowTeacherRefreshLog(false)}
                            style={{ background: "none", border: "none", color: "#6B7280", cursor: "pointer", fontSize: "0.75rem" }}
                          >
                            ✕ Close
                          </button>
                        </div>
                        <pre style={{
                          fontSize: "0.72rem", color: "#1F2937", background: "#ECFDF5",
                          border: "1px solid #BBF7D0", borderRadius: "6px",
                          padding: "0.6rem", maxHeight: "180px", overflowY: "auto",
                          whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0,
                          fontFamily: "'Courier New', monospace",
                        }}>
                          {teacherHpcRefreshLog}
                        </pre>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: "10px", marginBottom: "1rem", overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.65rem 1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <AlertCircle size={18} color="#D97706" />
                        <div style={{ fontSize: "0.86rem" }}>
                          <b style={{ color: "#92400E" }}>Not connected to PARAKH.</b>{" "}
                          <span style={{ color: "#B45309" }}>Connect to read your class from PARAKH. The list below is from your last fetch.</span>
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {/* Refresh even when not connected — will attempt re-login */}
                        <button
                          id="btn-refresh-parakh-session-inactive"
                          onClick={handleRefreshTeacherSession}
                          disabled={teacherHpcRefreshing}
                          style={{
                            display: "flex", alignItems: "center", gap: "0.35rem",
                            padding: "0.32rem 0.75rem", fontSize: "0.8rem", fontWeight: 600,
                            borderRadius: "6px", border: "1px solid #D97706",
                            background: "#FFFBEB", color: "#92400E",
                            cursor: teacherHpcRefreshing ? "not-allowed" : "pointer",
                          }}
                          title="Reconnect to PARAKH (you will type a captcha)"
                        >
                          <RefreshCw size={13} style={{ animation: teacherHpcRefreshing ? "spin 1s linear infinite" : "none" }} />
                          {teacherHpcRefreshing ? "Reconnecting…" : "Reconnect"}
                        </button>
                        <button onClick={() => { setShowTeacherHpcPanel(true); window.scrollTo({ top: 0, behavior: "smooth" }); }} className="btn btn-primary btn-sm">
                          <KeyRound size={13} /> Connect to PARAKH
                        </button>
                      </div>
                    </div>
                    {/* Collapsible refresh log when inactive */}
                    {showTeacherRefreshLog && teacherHpcRefreshLog && (
                      <div style={{ borderTop: "1px solid #FDE68A", background: "#FFFBEB", padding: "0.75rem 1rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                          <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#92400E" }}>🖥️ Refresh Log</span>
                          <button onClick={() => setShowTeacherRefreshLog(false)} style={{ background: "none", border: "none", color: "#6B7280", cursor: "pointer", fontSize: "0.75rem" }}>✕ Close</button>
                        </div>
                        <pre style={{ fontSize: "0.72rem", color: "#1F2937", background: "#FEF3C7", border: "1px solid #FDE68A", borderRadius: "6px", padding: "0.6rem", maxHeight: "160px", overflowY: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0, fontFamily: "'Courier New', monospace" }}>{teacherHpcRefreshLog}</pre>
                      </div>
                    )}
                  </div>
                )}

                {/* Stage switcher bar if multiple stages are assigned */}
                {renderTeacherStageSwitcher()}

                {/* Filter & Search Bar */}
                <div className="roster-controls-bar">
                  <div className="roster-search-input">
                    <Search size={16} color="var(--text-light)" />
                    <input
                      type="text"
                      placeholder="Search student name, APAAR ID, or admission no..."
                      value={studentSearch}
                      onChange={(e) => setStudentSearch(e.target.value)}
                    />
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                    <select
                      className="roster-filter-select"
                      value={studentGenderFilter}
                      onChange={(e) => setStudentGenderFilter(e.target.value)}
                    >
                      <option value="ALL">All Genders</option>
                      <option value="Male">Boys (Male)</option>
                      <option value="Female">Girls (Female)</option>
                    </select>

                    <select
                      className="roster-filter-select"
                      value={studentStatusFilter}
                      onChange={(e) => setStudentStatusFilter(e.target.value)}
                    >
                      <option value="ALL">All Status</option>
                      <option value="COMPLETED">Completed</option>
                      <option value="IN_PROGRESS">In Progress</option>
                      <option value="PENDING">Pending</option>
                    </select>

                    <button
                      onClick={() => loadTeacherRoster(activeTeacherStage)}
                      className="btn btn-outline"
                      title="Reload cached roster"
                      style={{ padding: "0.45rem 0.75rem" }}
                    >
                      <RefreshCw size={14} />
                    </button>
                  </div>
                </div>

                {/* Metrics strip */}
                {students.length > 0 && (() => {
                  const boysCount = students.filter((s) => {
                    const g = (s.gender || "").toLowerCase().trim();
                    return ["male", "m", "boy", "1"].includes(g);
                  }).length;
                  const girlsCount = students.filter((s) => {
                    const g = (s.gender || "").toLowerCase().trim();
                    return ["female", "f", "girl", "2"].includes(g);
                  }).length;
                  const completedCount = students.filter((s) => (s.status || "").toUpperCase() === "COMPLETED" || (s.status || "").toUpperCase() === "SUCCESS").length;
                  const inProgressCount = students.filter((s) => (s.status || "").toUpperCase() === "IN_PROGRESS").length;
                  const pendingCount = students.length - completedCount - inProgressCount;

                  return (
                    <div className="roster-metrics-strip">
                      <div className="roster-metric-pill">
                        <div className="lbl">Total Students</div>
                        <div className="val">{students.length}</div>
                      </div>
                      <div className="roster-metric-pill">
                        <div className="lbl">Boys / Girls</div>
                        <div className="val" style={{ fontSize: "1.05rem" }}>{boysCount} 👦 / {girlsCount} 👧</div>
                      </div>
                      <div className="roster-metric-pill">
                        <div className="lbl">In Progress</div>
                        <div className="val" style={{ color: "var(--kesari-600)" }}>{inProgressCount}</div>
                      </div>
                      <div className="roster-metric-pill">
                        <div className="lbl">Completed</div>
                        <div className="val" style={{ color: "var(--green-600)" }}>{completedCount}</div>
                      </div>
                      <div className="roster-metric-pill">
                        <div className="lbl">Pending / Unfilled</div>
                        <div className="val" style={{ color: "var(--text-muted)" }}>{pendingCount}</div>
                      </div>
                      <div className="roster-metric-pill">
                        <div className="lbl">Offline Excel</div>
                        <div className="val" style={{ color: "var(--chakra-blue)", fontSize: "0.95rem" }}>Pre-filled ✓</div>
                      </div>
                    </div>
                  );
                })()}

                {fetchJob?.status === "RUNNING" && <FetchProgress job={fetchJob} />}

                {/* Table Content */}
                {(() => {
                  if (studentsLoading && students.length === 0) {
                    return (
                      <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-muted)" }}>
                        <RefreshCw size={36} className="spin" style={{ margin: "0 auto 1rem", color: "var(--chakra-blue)" }} />
                        <div style={{ fontWeight: 700, fontSize: "1.05rem" }}>Connecting to PARAKH Portal...</div>
                        <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>Reading student records from PARAKH for {activeTeacherStage} Stage</div>
                      </div>
                    );
                  }

                  if (students.length === 0) {
                    return (
                      <div className="empty-roster-box">
                        <FileSpreadsheet size={48} color="#CF4A0A" style={{ margin: "0 auto 1rem", opacity: 0.6 }} />
                        <h3 style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--chakra-navy)" }}>
                          No Students Synced for {activeTeacherStage} Stage Yet
                        </h3>
                        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", maxWidth: 520, margin: "0.5rem auto 1.5rem" }}>
                          Connect with PARAKH HPC to fetch your assigned classroom student list automatically into your offline grading workbook.
                        </p>
                        <button
                          onClick={() => handleSyncRoster(activeTeacherStage)}
                          className="btn btn-primary"
                          disabled={loading || studentsLoading}
                          style={{ padding: "0.75rem 1.6rem", fontSize: "0.95rem" }}
                        >
                          <RefreshCw size={18} /> Fetch {activeTeacherStage} Roster from PARAKH
                        </button>
                      </div>
                    );
                  }

                  const query = studentSearch.trim().toLowerCase();
                  const filtered = students.filter((s) => {
                    if (query) {
                      const matchName = (s.student_name || "").toLowerCase().includes(query);
                      const matchAdm = (s.admission_number || "").toLowerCase().includes(query);
                      const matchApaar = (s.apaar_id || "").toLowerCase().includes(query);
                      const matchReg = (s.hpc_login_id || "").toLowerCase().includes(query);
                      if (!matchName && !matchAdm && !matchApaar && !matchReg) return false;
                    }
                    if (studentGenderFilter !== "ALL") {
                      const g = (s.gender || "").toLowerCase().trim();
                      const MALE_VALUES = ["male", "m", "boy", "1"];
                      const FEMALE_VALUES = ["female", "f", "girl", "2"];
                      if (studentGenderFilter === "Male" && !MALE_VALUES.includes(g)) return false;
                      if (studentGenderFilter === "Female" && !FEMALE_VALUES.includes(g)) return false;
                    }
                    if (studentStatusFilter !== "ALL") {
                      const st = (s.status || "").toUpperCase();
                      if (studentStatusFilter === "COMPLETED" && st !== "COMPLETED" && st !== "SUCCESS") return false;
                      if (studentStatusFilter === "IN_PROGRESS" && st !== "IN_PROGRESS") return false;
                      if (studentStatusFilter === "PENDING" && (st === "COMPLETED" || st === "IN_PROGRESS")) return false;
                    }
                    return true;
                  });

                  if (filtered.length === 0) {
                    return (
                      <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--text-muted)" }}>
                        <Search size={32} style={{ margin: "0 auto 0.5rem", opacity: 0.4 }} />
                        <div style={{ fontWeight: 600 }}>No students matching "{studentSearch}"</div>
                        <button onClick={() => { setStudentSearch(""); setStudentGenderFilter("ALL"); setStudentStatusFilter("ALL"); }} className="btn btn-outline" style={{ marginTop: "0.75rem", fontSize: "0.82rem" }}>
                          Clear Search Filters
                        </button>
                      </div>
                    );
                  }

                  return (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th style={{ width: 45 }}>#</th>
                            <th>Student Name</th>
                            <th>HPC Reg / Adm ID</th>
                            <th>APAAR ID</th>
                            <th>Grade &amp; Section</th>
                            <th>Gender</th>
                            <th>PARAKH Status</th>
                            <th>HPC Card</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((s, idx) => {
                            const rawStatus = (s.status || "PENDING").toUpperCase();
                            const isDone = rawStatus === "COMPLETED" || rawStatus === "SUCCESS";
                            const isProg = rawStatus === "IN_PROGRESS";
                            const statusCls = isDone ? "completed" : (isProg ? "in-progress" : "pending");

                            const { label: genderLabel, cls: avatarCls } = genderInfo(s.gender);
                            const initials = (s.student_name || "S").split(" ").map((n) => n[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();

                            return (
                              <tr key={s.student_id || idx}>
                                <td style={{ color: "var(--text-light)", fontWeight: 600 }}>{idx + 1}</td>
                                <td>
                                  <div className="student-name-cell">
                                    <div className={`student-avatar ${avatarCls}`}>{initials}</div>
                                    <div>
                                      <div style={{ fontWeight: 700, color: "var(--chakra-navy)" }}>{s.student_name}</div>
                                      <div style={{ fontSize: "0.74rem", color: "var(--text-light)" }}>
                                        {s.mother_tongue ? `Mother Tongue: ${s.mother_tongue}` : ""}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td>
                                  <span className="mono-chip">
                                    {s.hpc_login_id || s.admission_number || "—"}
                                  </span>
                                </td>
                                <td>
                                  {s.apaar_id ? (
                                    <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                                      <span className="mono-chip" style={{ color: "var(--brand-600)", fontWeight: 600 }}>
                                        {s.apaar_id}
                                      </span>
                                      <button
                                        type="button"
                                        className="copy-mini-btn"
                                        title="Copy APAAR ID"
                                        onClick={() => {
                                          navigator.clipboard.writeText(s.apaar_id || "");
                                          setCopiedId(s.apaar_id || null);
                                          setTimeout(() => setCopiedId(null), 2000);
                                        }}
                                      >
                                        {copiedId === s.apaar_id ? <Check size={13} color="#046A38" /> : <Copy size={13} />}
                                      </button>
                                    </div>
                                  ) : (
                                    <span style={{ color: "var(--text-light)", fontSize: "0.8rem" }}>—</span>
                                  )}
                                </td>
                                <td>
                                  <b>{s.grade || user.assigned_grade}</b>
                                  <span style={{ color: "var(--text-muted)", marginLeft: "0.3rem" }}>Sec {s.section || user.assigned_section || "—"}</span>
                                </td>
                                <td>
                                  <span style={{ fontSize: "0.84rem", fontWeight: 600, color: avatarCls === "female" ? "#9D174D" : avatarCls === "male" ? "#3730A3" : "var(--text-muted)" }}>
                                    {genderLabel}
                                  </span>
                                </td>
                                <td>
                                  <span className={`status-tag ${statusCls}`}>
                                    {isDone && <CheckCircle2 size={12} />}
                                    {isProg && <Clock size={12} />}
                                    {rawStatus.replace("_", " ")}
                                  </span>
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="btn btn-outline"
                                    style={{ padding: "0.3rem 0.7rem", fontSize: "0.8rem" }}
                                    onClick={() => setOpenCard({ id: s.student_id, name: s.student_name })}
                                    disabled={!teacherHpcStatus?.logged_in}
                                    title={teacherHpcStatus?.logged_in ? "Fill in this student's HPC card" : "Connect your PARAKH session first"}
                                  >
                                    <FilePenLine size={13} /> Open card
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>
            )}

            {openCard && (
              <HpcCardEditor
                api={cardsApi}
                stage={activeTeacherStage}
                studentId={openCard.id}
                studentName={openCard.name}
                onClose={() => setOpenCard(null)}
                onSubmitted={(id, status) =>
                  setStudents((prev) => prev.map((st) => (st.student_id === id ? { ...st, status } : st)))
                }
              />
            )}
          </div>
        )}
          </>} />
        </Routes>
        </main>

        <footer className="shell-footer" role="contentinfo">
          Teacher Assist is an independent tool. It is not an official government service and is not made by, or connected with,
          NCERT, PARAKH or the Ministry of Education.
        </footer>
      </div>
    </div>
  );
}

interface FetchJob {
  status: "RUNNING" | "COMPLETED" | "FAILED";
  stages: string[];
  stage_now: string | null;
  rosters: Record<string, number>;
  done: number;
  total: number;
  seconds_left: number;
  summary: string;
  notes?: string[];                 // e.g. students PARAKH lists that this login may not open
  error: string | null;
}

/** "Fetch from PARAKH" while it runs: which stage, how many students read of how many, time left. */
function FetchProgress({ job }: { job: FetchJob }) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const left = job.seconds_left > 90 ? `about ${Math.round(job.seconds_left / 60)} min left` : job.seconds_left ? "less than 2 min left" : "";
  return (
    <div className="fetch-progress" role="status" aria-live="polite">
      <div className="fetch-progress-head">
        <RefreshCw size={16} className="spin" aria-hidden="true" />
        <b>Fetching from PARAKH…</b>
        <span>
          {job.total ? `${job.stage_now ? `Reading ${job.stage_now}: ` : ""}${job.done} of ${job.total} students` : "Reading your class lists"}
          {left ? ` · ${left}` : ""}
        </span>
      </div>
      <div className="progress-bar-container" role="progressbar" aria-label="Students read" aria-valuemin={0} aria-valuemax={job.total || 1} aria-valuenow={job.done}>
        <div className="progress-fill" style={{ width: `${Math.max(pct, job.total ? 2 : 0)}%`, transition: "width 0.6s ease" }} />
      </div>
      <p>Every student's whole card is read once (the safe speed for PARAKH), so this takes a few minutes. You can keep working or leave this page.</p>
    </div>
  );
}

type PageInfo = { title: string; desc: string };
const PAGES: Record<string, PageInfo> = {
  roster: { title: "Students", desc: "Your class as on PARAKH. Open any student's card from here." },
  activities: { title: "Activities", desc: "Choose an activity and the three levels for each subject (Part B)." },
  bulk: { title: "Common answers", desc: "Answers most of the class shares - fill them once, change the few who differ." },
  settings: { title: "Class settings", desc: "Working days, max marks, medium and declaration for the whole class." },
  upload: { title: "Excel & upload", desc: "Download the class file, fill it, and send everything to PARAKH." },
  school_teachers: { title: "Teachers", desc: "Teacher accounts, their classes and their PARAKH connection." },
  school_students: { title: "Students", desc: "Every class's students and how far their cards are." },
  library: { title: "Activity Library", desc: "Activities from PARAKH, your school's versions and your own." },
};

const TEACHER_STEPS: { id: "roster" | "activities" | "bulk" | "settings" | "upload"; label: string; hint: string; icon: typeof Users }[] = [
  { id: "roster", label: "Students", hint: "Your class from PARAKH", icon: Users },
  { id: "activities", label: "Activities", hint: "Part B for every subject", icon: CheckCircle2 },
  { id: "bulk", label: "Common answers", hint: "Same answer for many", icon: Layers },
  { id: "settings", label: "Class settings", hint: "Days, marks, medium", icon: SlidersHorizontal },
  { id: "upload", label: "Excel & upload", hint: "Download, fill, send", icon: Upload },
];
