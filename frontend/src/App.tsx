import React, { useState, useEffect, useCallback } from "react";
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
  Trash2,
  FileCheck2,
  Sparkles,
  Check,
  Eye,
  EyeOff,
  Lock,
  Smartphone,
  Save,
  PlayCircle,
  StopCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000/api/v1";

// ─── Types ─────────────────────────────────────────────────────────────────

interface UserInfo {
  token: string;
  role: "SCHOOL_ADMIN" | "TEACHER";
  name: string;
  user_id: string;
  school_id?: string;
  school_name?: string;
  assigned_stage?: string;
  assigned_grade?: string;
  assigned_section?: string;
}

interface TeacherItem {
  id: string;
  teacher_name: string;
  username: string;
  assigned_stage: string;
  assigned_grade: string;
  assigned_section: string;
  is_active: boolean;
  parakh_connected: boolean;
  parakh_user?: string;
  has_hpc_credentials: boolean;
}

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
}

type StatusMsg = { type: "success" | "error" | "info" | "warning"; text: string } | null;
type AuthTab = "admin_login" | "teacher_login" | "register";
type TeacherTab = "session" | "upload" | "roster";

// ─── App ───────────────────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authTab, setAuthTab] = useState<AuthTab>("admin_login");

  // Auth form
  const [adminIdentifier, setAdminIdentifier] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
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
  const [newTeacherStage, setNewTeacherStage] = useState("Middle");
  const [newTeacherGrade, setNewTeacherGrade] = useState("Grade 6");
  const [newTeacherSection, setNewTeacherSection] = useState("A");

  // HPC Session – School
  const [schoolHpcStatus, setSchoolHpcStatus] = useState<HpcStatus | null>(null);
  const [showSchoolHpcPanel, setShowSchoolHpcPanel] = useState(false);
  const [schoolHpcLoginId, setSchoolHpcLoginId] = useState("");
  const [schoolHpcPassword, setSchoolHpcPassword] = useState("");
  const [showSchoolHpcPwd, setShowSchoolHpcPwd] = useState(false);
  const [schoolHpcLoading, setSchoolHpcLoading] = useState(false);
  const [schoolHpcOtpStep, setSchoolHpcOtpStep] = useState(false);
  const [schoolHpcOtp, setSchoolHpcOtp] = useState("");

  // HPC Session – Teacher
  const [teacherHpcStatus, setTeacherHpcStatus] = useState<HpcStatus | null>(null);
  const [showTeacherHpcPanel, setShowTeacherHpcPanel] = useState(false);
  const [teacherHpcLoginId, setTeacherHpcLoginId] = useState("");
  const [teacherHpcPassword, setTeacherHpcPassword] = useState("");
  const [showTeacherHpcPwd, setShowTeacherHpcPwd] = useState(false);
  const [teacherHpcLoading, setTeacherHpcLoading] = useState(false);
  const [teacherHpcOtpStep, setTeacherHpcOtpStep] = useState(false);
  const [teacherHpcOtp, setTeacherHpcOtp] = useState("");

  // Teacher workspace
  const [teacherTab, setTeacherTab] = useState<TeacherTab>("session");
  const [validationReport, setValidationReport] = useState<any>(null);
  const [uploadedFileName, setUploadedFileName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // ─── Init ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    const stored = localStorage.getItem("hpc_auth_session");
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem("hpc_auth_session");
      }
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    if (user.role === "SCHOOL_ADMIN") {
      fetchSchoolData();
      fetchSchoolHpcStatus();
    } else {
      fetchTeacherHpcStatus();
    }
  }, [user?.user_id]);

  // ─── API Helpers ─────────────────────────────────────────────────────────

  const authHeaders = useCallback(() => ({
    Authorization: `Bearer ${user?.token}`,
    "Content-Type": "application/json",
  }), [user?.token]);

  const apiGet = async (path: string) => {
    const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
    return res;
  };

  const apiPost = async (path: string, body?: any) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return res;
  };

  // ─── School Admin ─────────────────────────────────────────────────────────

  const fetchSchoolData = async () => {
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
  };

  const fetchSchoolHpcStatus = async () => {
    if (!user || user.role !== "SCHOOL_ADMIN") return;
    try {
      const res = await apiGet("/school/hpc/status");
      if (res.ok) setSchoolHpcStatus(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateTeacher = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    setLoading(true);
    setStatusMsg(null);
    try {
      const res = await apiPost("/school/teachers", {
        teacher_name: newTeacherName,
        username: newTeacherUsername,
        password: newTeacherPassword,
        assigned_stage: newTeacherStage,
        assigned_grade: newTeacherGrade,
        assigned_section: newTeacherSection,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: `Teacher '${data.teacher_name}' created for ${data.assigned_grade}-${data.assigned_section}!` });
        setShowAddTeacherModal(false);
        setNewTeacherName(""); setNewTeacherUsername(""); setNewTeacherPassword("");
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

  const handleDeleteTeacher = async (teacherId: string) => {
    if (!user || !confirm("Remove this teacher account?")) return;
    try {
      const res = await fetch(`${API_BASE}/school/teachers/${teacherId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (res.ok) {
        setStatusMsg({ type: "success", text: "Teacher removed." });
        fetchSchoolData();
      }
    } catch (e) { console.error(e); }
  };

  // ─── School HPC Session ───────────────────────────────────────────────────

  const handleSaveSchoolHpcCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setSchoolHpcLoading(true);
    try {
      const res = await apiPost("/school/hpc/save-credentials", {
        hpc_login_id: schoolHpcLoginId,
        hpc_password: schoolHpcPassword,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: "✅ HPC credentials saved! Now click 'Start Session'." });
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
    setStatusMsg({ type: "info", text: "🔄 Auto-solving captcha and connecting to PARAKH HPC..." });
    try {
      const body: any = {};
      if (schoolHpcLoginId) body.hpc_login_id = schoolHpcLoginId;
      if (schoolHpcPassword) body.hpc_password = schoolHpcPassword;
      const res = await apiPost("/school/hpc/start-session", body);
      const data = await res.json();
      if (res.ok) {
        if (data.status === "otp_required") {
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

  const fetchTeacherHpcStatus = async () => {
    if (!user || user.role !== "TEACHER") return;
    try {
      const res = await apiGet("/teacher/hpc/status");
      if (res.ok) setTeacherHpcStatus(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleSaveTeacherHpcCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setTeacherHpcLoading(true);
    try {
      const res = await apiPost("/teacher/hpc/save-credentials", {
        hpc_login_id: teacherHpcLoginId,
        hpc_password: teacherHpcPassword,
      });
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: "✅ HPC credentials saved! Now click 'Start Session'." });
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
    setStatusMsg({ type: "info", text: "🔄 Auto-solving captcha and connecting to PARAKH HPC..." });
    try {
      const body: any = {};
      if (teacherHpcLoginId) body.hpc_login_id = teacherHpcLoginId;
      if (teacherHpcPassword) body.hpc_password = teacherHpcPassword;
      const res = await apiPost("/teacher/hpc/start-session", body);
      const data = await res.json();
      if (res.ok) {
        if (data.status === "otp_required") {
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

  // ─── Teacher Roster & Upload ──────────────────────────────────────────────

  const handleSyncRoster = async () => {
    setLoading(true);
    setStatusMsg({ type: "info", text: "Connecting to PARAKH portal to fetch your class roster..." });
    try {
      const res = await apiPost("/teacher/roster/sync");
      const data = await res.json();
      if (res.ok) {
        setStatusMsg({ type: "success", text: `✅ Retrieved ${data.total_students} students from PARAKH!` });
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Roster fetch failed." });
      }
    } catch (e: any) {
      setStatusMsg({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadExcel = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/teacher/roster/download`, {
        headers: { Authorization: `Bearer ${user?.token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `HPC_${user?.assigned_stage}_${user?.assigned_grade}_${user?.assigned_section}_Grading.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        setStatusMsg({ type: "success", text: "Excel workbook downloaded!" });
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
    setLoading(true);
    setStatusMsg(null);
    setUploadedFileName(file.name);

    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/teacher/upload/validate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
        body: formData,
      });
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
    setUploadProgress(20);
    setStatusMsg({ type: "info", text: "Initiating automated submission to PARAKH portal..." });
    try {
      const res = await fetch(`${API_BASE}/teacher/upload/submit?file_name=${encodeURIComponent(uploadedFileName)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      const job = await res.json();
      if (res.ok) {
        setUploadProgress(100);
        setStatusMsg({ type: "success", text: `Job #${job.job_id?.substring(0, 8)} started! Status: ${job.status}` });
      } else {
        setStatusMsg({ type: "error", text: job.detail || "Submission failed." });
      }
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Auth ─────────────────────────────────────────────────────────────────

  const handleLogin = async (e: React.FormEvent, role: "SCHOOL_ADMIN" | "TEACHER") => {
    e.preventDefault();
    setLoading(true);
    setStatusMsg(null);
    const identifier = role === "SCHOOL_ADMIN" ? adminIdentifier.trim() : teacherUsername.trim();
    const password = role === "SCHOOL_ADMIN" ? adminPassword : teacherPassword;
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier, password, role }),
      });
      const data = await res.json();
      if (res.ok) {
        const userInfo: UserInfo = {
          token: data.access_token,
          role: data.role,
          name: data.name,
          user_id: data.user_id,
          school_id: data.school_id,
          school_name: data.school_name,
          assigned_stage: data.assigned_stage,
          assigned_grade: data.assigned_grade,
          assigned_section: data.assigned_section,
        };
        setUser(userInfo);
        localStorage.setItem("hpc_auth_session", JSON.stringify(userInfo));
        setStatusMsg({ type: "success", text: `Welcome back, ${data.name}!` });
      } else {
        setStatusMsg({ type: "error", text: data.detail || "Invalid credentials." });
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
      const res = await fetch(`${API_BASE}/auth/school/register`, {
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

  const handleLogout = () => {
    localStorage.removeItem("hpc_auth_session");
    setUser(null);
    setStatusMsg({ type: "info", text: "Logged out successfully." });
  };

  // ─── Sub-components ───────────────────────────────────────────────────────

  /** Reusable HPC Session Panel shown on both dashboards */
  const HpcSessionPanel = ({
    role,
    hpcStatus,
    loading: hpcLoad,
    loginId, setLoginId,
    password: pwd, setPassword,
    showPwd, setShowPwd,
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
    showPwd: boolean; setShowPwd: (v: boolean) => void;
    otpStep: boolean; otp: string; setOtp: (v: string) => void;
    onSaveCredentials: (e: React.FormEvent) => void;
    onStartSession: () => void;
    onVerifyOtp: (e: React.FormEvent) => void;
    onEndSession: () => void;
    onRefreshStatus: () => void;
    showPanel: boolean; setShowPanel: (v: boolean) => void;
  }) => {
    const isActive = hpcStatus?.logged_in;

    return (
      <div
        className="ui-panel"
        style={{
          borderLeft: `4px solid ${isActive ? "var(--green-500)" : "var(--kesari-500)"}`,
          padding: 0,
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.4rem",
            background: isActive ? "var(--green-50)" : "var(--kesari-50)",
            cursor: "pointer",
          }}
          onClick={() => setShowPanel(!showPanel)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                backgroundColor: isActive ? "var(--green-500)" : "#F59E0B",
                boxShadow: isActive ? "0 0 8px #10B981" : "0 0 8px #F59E0B",
              }}
            />
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.95rem", color: isActive ? "#065F46" : "#9A3412" }}>
                {isActive
                  ? `🟢 ${role === "school" ? "School" : "Teacher"} HPC Session Active`
                  : `🟠 ${role === "school" ? "School" : "Teacher"} HPC Session Inactive`}
              </div>
              <div style={{ fontSize: "0.80rem", color: isActive ? "#047857" : "#B45309" }}>
                {isActive
                  ? `Connected as ${hpcStatus?.user || "HPC User"} · ${hpcStatus?.school || ""}`
                  : `Save your ${role === "school" ? "School" : "Teacher"} HPC credentials, then start the session`}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              onClick={(e) => { e.stopPropagation(); onRefreshStatus(); }}
              className="btn btn-outline"
              style={{ padding: "0.3rem 0.6rem", fontSize: "0.78rem" }}
              title="Refresh status"
            >
              <RefreshCw size={13} />
            </button>
            {isActive && (
              <button
                onClick={(e) => { e.stopPropagation(); onEndSession(); }}
                className="btn btn-outline"
                disabled={hpcLoad}
                style={{ padding: "0.3rem 0.7rem", fontSize: "0.78rem", color: "var(--danger-500)", borderColor: "#FCA5A5" }}
                title="End HPC session"
              >
                <StopCircle size={13} /> End Session
              </button>
            )}
            {showPanel ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
        </div>

        {/* Expandable Body */}
        {showPanel && (
          <div style={{ padding: "1.4rem" }}>
            {/* OTP Step */}
            {otpStep ? (
              <form onSubmit={onVerifyOtp} style={{ maxWidth: 420 }}>
                <div className="alert-box alert-info" style={{ marginBottom: "1.2rem" }}>
                  <Smartphone size={18} color="#003399" />
                  <div><b>OTP Verification:</b> Enter the 6-digit code sent to your registered mobile.</div>
                </div>
                <div className="form-group" style={{ marginBottom: "1rem" }}>
                  <label className="form-label">6-Digit OTP</label>
                  <input
                    type="text"
                    maxLength={8}
                    className="form-input text-center"
                    style={{ fontSize: "1.4rem", letterSpacing: "0.35rem", fontWeight: 700 }}
                    placeholder="••••••"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                    required
                    autoFocus
                  />
                </div>
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <button type="submit" className="btn btn-green" style={{ flex: 1 }} disabled={hpcLoad || otp.length < 4}>
                    <Check size={16} /> {hpcLoad ? "Verifying..." : "Confirm OTP"}
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => setOtp("")} disabled={hpcLoad}>
                    Clear
                  </button>
                </div>
              </form>
            ) : isActive ? (
              /* Already connected */
              <div className="alert-box alert-success" style={{ margin: 0 }}>
                <CheckCircle2 size={20} color="#046A38" />
                <div>
                  <b>Session Active.</b> HPC portal operations (roster sync, uploads) are unlocked.
                  Click <b>End Session</b> in the header bar to log out from PARAKH HPC.
                </div>
              </div>
            ) : (
              /* Credentials + Start */
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
                {/* Left: Save Credentials */}
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.88rem", color: "var(--chakra-navy)", marginBottom: "0.8rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Save size={15} /> Save HPC Credentials
                  </div>
                  <form onSubmit={onSaveCredentials}>
                    <div className="form-group" style={{ marginBottom: "0.8rem" }}>
                      <label className="form-label" style={{ fontSize: "0.82rem" }}>
                        {role === "school" ? "School HPC Login ID / Mobile" : "Teacher HPC Staff Code / ID"}
                      </label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. 9876543210 or SCH_101"
                        value={loginId}
                        onChange={(e) => setLoginId(e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: "0.8rem" }}>
                      <label className="form-label" style={{ fontSize: "0.82rem" }}>HPC Portal Password</label>
                      <div style={{ position: "relative" }}>
                        <input
                          type={showPwd ? "text" : "password"}
                          className="form-input"
                          placeholder="••••••••••"
                          value={pwd}
                          onChange={(e) => setPassword(e.target.value)}
                          required
                          style={{ paddingRight: "2.5rem" }}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPwd(!showPwd)}
                          style={{ position: "absolute", right: "0.75rem", top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
                        >
                          {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>
                    <button type="submit" className="btn btn-outline" style={{ width: "100%", fontSize: "0.85rem" }} disabled={hpcLoad}>
                      <Save size={14} /> Save Credentials
                    </button>
                  </form>
                </div>

                {/* Right: Start Session */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", borderLeft: "1px solid var(--border-light)", paddingLeft: "1.5rem" }}>
                  <div style={{ textAlign: "center", marginBottom: "1rem" }}>
                    <Lock size={32} color="#003399" style={{ margin: "0 auto 0.5rem" }} />
                    <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "var(--chakra-navy)" }}>
                      Auto-Login to PARAKH HPC ({role === "school" ? "School Account" : "Teacher Account"})
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.3rem", lineHeight: 1.5 }}>
                      Captcha is solved automatically.<br />No manual steps needed.
                    </div>
                  </div>
                  <button
                    onClick={onStartSession}
                    className="btn btn-saffron"
                    disabled={hpcLoad}
                    style={{ padding: "0.75rem 1.8rem", fontSize: "0.95rem", fontWeight: 700, width: "100%" }}
                  >
                    <PlayCircle size={18} />
                    {hpcLoad ? "Connecting..." : "Start HPC Session"}
                  </button>
                  {hpcLoad && (
                    <div style={{ marginTop: "0.75rem", fontSize: "0.78rem", color: "var(--text-muted)", textAlign: "center" }}>
                      Fetching captcha &amp; authenticating...
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <div className="tricolor-stripe" />

      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="brand-badge">
            <div className="emblem-wrapper">
              <svg viewBox="0 0 100 100" width="36" height="36">
                <circle cx="50" cy="50" r="46" fill="#003399" />
                <circle cx="50" cy="50" r="39" fill="white" />
                <circle cx="50" cy="50" r="11" fill="#003399" />
                <g stroke="#003399" strokeWidth="2.4">
                  {[...Array(24)].map((_, i) => (
                    <line
                      key={i}
                      x1="50" y1="50"
                      x2={50 + 38 * Math.cos((i * 15 * Math.PI) / 180)}
                      y2={50 + 38 * Math.sin((i * 15 * Math.PI) / 180)}
                    />
                  ))}
                </g>
              </svg>
            </div>
            <div className="brand-titles">
              <h1>PARAKH <span className="kesari">राष्ट्रीय समग्र</span> <span className="green">प्रगति पत्रक</span></h1>
              <div className="brand-sub">National Holistic Progress Card (HPC) · Ministry of Education, Govt. of India</div>
            </div>
          </div>
          <div className="user-menu">
            {user ? (
              <>
                <div className="role-chip">
                  <span className="role-badge">{user.role === "SCHOOL_ADMIN" ? "Principal / Admin" : "Teacher"}</span>
                  <span>{user.name}</span>
                  {user.school_name && <span style={{ color: "var(--text-light)" }}>({user.school_name})</span>}
                </div>
                <button onClick={handleLogout} className="btn btn-outline" style={{ padding: "0.4rem 0.85rem", fontSize: "0.82rem" }}>
                  <LogOut size={15} /> Logout
                </button>
              </>
            ) : (
              <span className="gov-pill" style={{ color: "var(--chakra-navy)", background: "var(--chakra-100)" }}>
                <ShieldCheck size={14} color="#003399" /> UDISE+ Official Verified
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="main-wrapper">
        {/* Status Alert */}
        {statusMsg && (
          <div className={`alert-box alert-${statusMsg.type}`}>
            {statusMsg.type === "success" && <CheckCircle2 size={18} />}
            {statusMsg.type === "error" && <AlertCircle size={18} />}
            {statusMsg.type === "info" && <ShieldCheck size={18} />}
            {statusMsg.type === "warning" && <AlertCircle size={18} />}
            <div style={{ flex: 1 }}>{statusMsg.text}</div>
            <button onClick={() => setStatusMsg(null)} style={{ background: "transparent", border: "none", cursor: "pointer", fontWeight: 700, color: "inherit" }}>✕</button>
          </div>
        )}

        {/* ── AUTH ──────────────────────────────────────────────────────── */}
        {!user && (
          <div>
            <div className="hero-card">
              <div className="hero-tag"><Sparkles size={14} /> National Education Policy (NEP 2020) Digital Assessment</div>
              <h2 className="hero-title">Empowering Schools &amp; Educators Nationwide</h2>
              <p className="hero-desc">
                Official single-school registration with UDISE+ verification. School Principals and Teachers each manage
                their own isolated HPC PARAKH sessions — captcha is solved automatically.
              </p>
              <div className="hero-badges-row">
                <span className="gov-pill">🏛️ One School = One UDISE Account</span>
                <span className="gov-pill">📚 Preparatory (Grades 3–5)</span>
                <span className="gov-pill">🔬 Middle (Grades 6–8)</span>
                <span className="gov-pill">⚡ Auto Captcha Solver</span>
              </div>
            </div>

            <div className="ui-panel" style={{ maxWidth: 750, margin: "0 auto" }}>
              <div className="tab-list">
                <button className={`tab-btn ${authTab === "admin_login" ? "active" : ""}`} onClick={() => { setAuthTab("admin_login"); setStatusMsg(null); }}>
                  <Building2 size={16} /> School Principal Login
                </button>
                <button className={`tab-btn ${authTab === "teacher_login" ? "active" : ""}`} onClick={() => { setAuthTab("teacher_login"); setStatusMsg(null); }}>
                  <GraduationCap size={16} /> Class Teacher Login
                </button>
                <button className={`tab-btn ${authTab === "register" ? "active" : ""}`} onClick={() => { setAuthTab("register"); setStatusMsg(null); }}>
                  <School size={16} /> Register School (UDISE+)
                </button>
              </div>

              {authTab === "admin_login" && (
                <form onSubmit={(e) => handleLogin(e, "SCHOOL_ADMIN")}>
                  <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                    <label className="form-label"><span>UDISE+ Code or Admin Email</span><span className="form-hint">11-digit code</span></label>
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
                      <label className="form-label">Official School Name *</label>
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
                      <input type="password" className="form-input" placeholder="Min 6 characters" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} required />
                    </div>
                  </div>
                  <button type="submit" className="btn btn-saffron" style={{ width: "100%" }} disabled={loading}>
                    <School size={16} /> {loading ? "Verifying & Registering..." : "Register School on PARAKH Hub"}
                  </button>
                </form>
              )}
            </div>
          </div>
        )}

        {/* ── SCHOOL ADMIN DASHBOARD ────────────────────────────────────── */}
        {user?.role === "SCHOOL_ADMIN" && (
          <div>
            <div className="hero-card" style={{ background: "linear-gradient(135deg, #041E42 0%, #163B70 100%)" }}>
              <div className="hero-tag"><Building2 size={14} /> School Administration Console</div>
              <h2 className="hero-title">{user.school_name || "School Command Center"}</h2>
              <div className="hero-badges-row" style={{ marginTop: "0.8rem" }}>
                <span className="gov-pill">🏷️ UDISE+: <b>{schoolStats?.udise_code || "Registered"}</b></span>
                <span className="gov-pill">👤 Admin: <b>{user.name}</b></span>
                <span className="gov-pill">🟢 MySQL Multi-Tenant Active</span>
              </div>
            </div>

            {/* School HPC Session Panel */}
            <HpcSessionPanel
              role="school"
              hpcStatus={schoolHpcStatus}
              loading={schoolHpcLoading}
              loginId={schoolHpcLoginId} setLoginId={setSchoolHpcLoginId}
              password={schoolHpcPassword} setPassword={setSchoolHpcPassword}
              showPwd={showSchoolHpcPwd} setShowPwd={setShowSchoolHpcPwd}
              otpStep={schoolHpcOtpStep}
              otp={schoolHpcOtp} setOtp={setSchoolHpcOtp}
              onSaveCredentials={handleSaveSchoolHpcCredentials}
              onStartSession={handleStartSchoolSession}
              onVerifyOtp={handleVerifySchoolOtp}
              onEndSession={handleEndSchoolSession}
              onRefreshStatus={fetchSchoolHpcStatus}
              showPanel={showSchoolHpcPanel}
              setShowPanel={setShowSchoolHpcPanel}
            />

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
                  <div className="kpi-subtext">Official PARAKH progress cards</div>
                </div>
                <div className="kpi-card purple">
                  <div className="kpi-top"><span className="kpi-label">Completion Rate</span><div className="kpi-icon purple"><FileCheck2 size={20} /></div></div>
                  <div className="kpi-number">{schoolStats.completion_rate_percent}%</div>
                  <div className="kpi-subtext">School-wide compliance target</div>
                </div>
              </div>
            )}

            {/* Teachers Table */}
            <div className="ui-panel">
              <div className="panel-header">
                <div className="panel-title"><Users size={20} color="#003399" /><span>Assigned Class Teachers Roster</span></div>
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
                        <th>Username</th>
                        <th>Stage</th>
                        <th>Class</th>
                        <th>HPC Session</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {teachers.map((t) => (
                        <tr key={t.id}>
                          <td><b>{t.teacher_name}</b></td>
                          <td><code style={{ fontSize: "0.82rem", background: "#F1F5F9", padding: "0.2rem 0.4rem", borderRadius: "4px" }}>{t.username}</code></td>
                          <td>
                            <span style={{ padding: "0.2rem 0.55rem", borderRadius: "4px", fontSize: "0.78rem", fontWeight: 700, background: t.assigned_stage === "Middle" ? "#FEF3C7" : "#E0F2FE", color: t.assigned_stage === "Middle" ? "#92400E" : "#0369A1" }}>
                              {t.assigned_stage}
                            </span>
                          </td>
                          <td><b>{t.assigned_grade}</b> - Sec {t.assigned_section}</td>
                          <td>
                            {t.parakh_connected
                              ? <span className="status-pill active">🟢 Active ({t.parakh_user || "HPC"})</span>
                              : <span className="status-pill inactive">{t.has_hpc_credentials ? "🟡 Credentials Saved" : "🔴 Not Connected"}</span>}
                          </td>
                          <td>
                            <button onClick={() => handleDeleteTeacher(t.id)} className="btn btn-outline" style={{ padding: "0.3rem 0.6rem", color: "var(--danger-500)", borderColor: "#FCA5A5" }}>
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Add Teacher Modal */}
            {showAddTeacherModal && (
              <div className="modal-overlay">
                <div className="modal-dialog">
                  <div className="modal-header">
                    <div className="modal-title">Provision New Class Teacher</div>
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
                      <div className="form-group" style={{ marginBottom: "1rem" }}>
                        <label className="form-label">Initial Password *</label>
                        <input type="password" className="form-input" placeholder="Min 6 characters" value={newTeacherPassword} onChange={(e) => setNewTeacherPassword(e.target.value)} required />
                      </div>
                      <div className="form-grid" style={{ marginBottom: 0 }}>
                        <div className="form-group">
                          <label className="form-label">HPC Stage *</label>
                          <select className="form-select" value={newTeacherStage} onChange={(e) => { const s = e.target.value; setNewTeacherStage(s); setNewTeacherGrade(s === "Preparatory" ? "Grade 3" : "Grade 6"); }}>
                            <option value="Preparatory">Preparatory (Grades 3-5)</option>
                            <option value="Middle">Middle (Grades 6-8)</option>
                          </select>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Assigned Grade *</label>
                          <select className="form-select" value={newTeacherGrade} onChange={(e) => setNewTeacherGrade(e.target.value)}>
                            {newTeacherStage === "Preparatory"
                              ? <><option value="Grade 3">Grade 3</option><option value="Grade 4">Grade 4</option><option value="Grade 5">Grade 5</option></>
                              : <><option value="Grade 6">Grade 6</option><option value="Grade 7">Grade 7</option><option value="Grade 8">Grade 8</option></>}
                          </select>
                        </div>
                        <div className="form-group">
                          <label className="form-label">Section *</label>
                          <select className="form-select" value={newTeacherSection} onChange={(e) => setNewTeacherSection(e.target.value)}>
                            <option value="A">Section A</option>
                            <option value="B">Section B</option>
                            <option value="C">Section C</option>
                            <option value="D">Section D</option>
                          </select>
                        </div>
                      </div>
                    </div>
                    <div className="modal-footer">
                      <button type="button" onClick={() => setShowAddTeacherModal(false)} className="btn btn-outline">Cancel</button>
                      <button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Creating..." : "Save & Assign Class"}</button>
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
            <div className="hero-card" style={{ background: "linear-gradient(135deg, #046A38 0%, #064E3B 100%)" }}>
              <div className="hero-tag" style={{ background: "rgba(255,255,255,0.2)", color: "#FFF", borderColor: "rgba(255,255,255,0.4)" }}>
                <GraduationCap size={14} /> Teacher Assessment Hub
              </div>
              <h2 className="hero-title">Welcome, {user.name}</h2>
              <p className="hero-desc">
                Classroom evaluation workspace for <b>{user.assigned_grade} · Section {user.assigned_section}</b> ({user.assigned_stage} Stage) at <b>{user.school_name}</b>.
              </p>
              <div className="hero-badges-row" style={{ marginTop: "0.8rem" }}>
                <span className="gov-pill">🏫 {user.school_name}</span>
                <span className="gov-pill">🎯 {user.assigned_stage} Stage</span>
                <span className="gov-pill">📌 {user.assigned_grade} - {user.assigned_section}</span>
              </div>
            </div>

            {/* Teacher HPC Session Panel */}
            <HpcSessionPanel
              role="teacher"
              hpcStatus={teacherHpcStatus}
              loading={teacherHpcLoading}
              loginId={teacherHpcLoginId} setLoginId={setTeacherHpcLoginId}
              password={teacherHpcPassword} setPassword={setTeacherHpcPassword}
              showPwd={showTeacherHpcPwd} setShowPwd={setShowTeacherHpcPwd}
              otpStep={teacherHpcOtpStep}
              otp={teacherHpcOtp} setOtp={setTeacherHpcOtp}
              onSaveCredentials={handleSaveTeacherHpcCredentials}
              onStartSession={handleStartTeacherSession}
              onVerifyOtp={handleVerifyTeacherOtp}
              onEndSession={handleEndTeacherSession}
              onRefreshStatus={fetchTeacherHpcStatus}
              showPanel={showTeacherHpcPanel}
              setShowPanel={setShowTeacherHpcPanel}
            />

            {/* Tabs */}
            <div className="tab-list">
              <button className={`tab-btn ${teacherTab === "upload" ? "active" : ""}`} onClick={() => setTeacherTab("upload")}>
                <Upload size={16} /> 1. Validate &amp; Upload
              </button>
              <button className={`tab-btn ${teacherTab === "roster" ? "active" : ""}`} onClick={() => setTeacherTab("roster")}>
                <FileSpreadsheet size={16} /> 2. Roster Sync &amp; Download
              </button>
            </div>

            {/* Tab 1: Upload */}
            {teacherTab === "upload" && (
              <div className="ui-panel">
                <div className="panel-header">
                  <div className="panel-title"><Upload size={20} color="#FF671F" /><span>Upload Completed Class Grading Sheet</span></div>
                </div>

                <label className="dropzone" style={{ display: "block", marginBottom: "1.5rem" }}>
                  <input type="file" accept=".xlsx" onChange={handleFileUpload} style={{ display: "none" }} />
                  <FileSpreadsheet size={42} color="#003399" style={{ margin: "0 auto 0.8rem" }} />
                  <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "var(--chakra-navy)" }}>
                    {uploadedFileName ? `Selected: ${uploadedFileName}` : "Click or Drag & Drop Graded Excel (.xlsx)"}
                  </div>
                  <div style={{ fontSize: "0.82rem", color: "var(--text-light)", marginTop: "0.25rem" }}>
                    Validates student rows against PARAKH portal rules, attendance, and character limits.
                  </div>
                </label>

                {validationReport && (
                  <div style={{ marginTop: "1.5rem" }}>
                    <div style={{ padding: "1rem 1.4rem", borderRadius: "12px", background: validationReport.is_valid ? "var(--green-50)" : "var(--danger-100)", border: `1px solid ${validationReport.is_valid ? "var(--green-500)" : "var(--danger-500)"}`, display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.2rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        {validationReport.is_valid ? <CheckCircle2 size={24} color="#046A38" /> : <AlertCircle size={24} color="#DC2626" />}
                        <div>
                          <div style={{ fontWeight: 800, fontSize: "1.05rem", color: validationReport.is_valid ? "#065F46" : "#991B1B" }}>
                            {validationReport.is_valid ? `Validation Passed · ${validationReport.total_records} Students` : `Validation Failed · ${validationReport.error_count} Error(s)`}
                          </div>
                          <div style={{ fontSize: "0.82rem", color: validationReport.is_valid ? "#047857" : "#B91C1C" }}>
                            Stage: <b>{validationReport.detected_stage}</b> | Days: <b>{validationReport.seeder_working_days}</b>
                          </div>
                        </div>
                      </div>
                      {validationReport.is_valid && (
                        <button onClick={handleStartSubmission} className="btn btn-green" disabled={isSubmitting} style={{ padding: "0.6rem 1.5rem" }}>
                          <Sparkles size={16} /> {isSubmitting ? "Submitting..." : "Start Automated Submission"}
                        </button>
                      )}
                    </div>

                    {isSubmitting && (
                      <div style={{ marginBottom: "1.5rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", fontWeight: 600 }}>
                          <span>Automating submissions...</span><span>{uploadProgress}%</span>
                        </div>
                        <div className="progress-bar-container"><div className="progress-fill" style={{ width: `${uploadProgress}%` }} /></div>
                      </div>
                    )}

                    {validationReport.errors?.length > 0 && (
                      <div className="data-table-wrapper">
                        <table className="data-table">
                          <thead><tr><th>Excel Row</th><th>Field</th><th>Validation Issue</th></tr></thead>
                          <tbody>
                            {validationReport.errors.map((err: any, idx: number) => (
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
                  <div className="panel-title"><FileSpreadsheet size={20} color="#046A38" /><span>Synchronize &amp; Download Official Class Roster</span></div>
                </div>
                <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>
                  Connects to PARAKH using your active HPC session, pulls your <b>{user.assigned_stage}</b> student roster,
                  and formats an offline Excel workbook with attendance and competency columns.
                </p>
                <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                  <button onClick={handleSyncRoster} className="btn btn-primary" disabled={loading}>
                    <RefreshCw size={16} /> {loading ? "Fetching Roster..." : "Fetch Class Roster from PARAKH"}
                  </button>
                  <button onClick={handleDownloadExcel} className="btn btn-saffron">
                    <Download size={16} /> Download Pre-Populated Excel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
