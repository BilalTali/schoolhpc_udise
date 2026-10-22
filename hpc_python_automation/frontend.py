"""
HPC Automation - Executive Web Dashboard & Management Portal
PARAKH Holistic Progress Card Automated Submission Suite
"""
import sys
import os

# Ensure Windows console handles UTF-8 without charmap errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
import time
import json
import pandas as pd
import streamlit as st

# Ensure root directory is in sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portal.student_fetcher import fetch_students_from_portal, generate_prepopulated_excel, fetch_global_activities_from_portal
from excel.importer import import_preparatory_workbook
from excel.validator import validate_workbook_records
from database.repository import UploadRepository
from database.models import UploadState
from portal.login import check_session_status, start_interactive_session, end_session, cleanup_zombie_browsers
import portal.uploader

# -----------------------------------------------------------------------------
# Streamlit Configuration & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PARAKH HPC Automation Hub",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Top Hero Header */
    .hero-container {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 40%, #0369A1 100%);
        border-radius: 20px;
        padding: 2.2rem 2.6rem;
        color: white;
        margin-bottom: 1.8rem;
        box-shadow: 0 12px 30px -8px rgba(15, 23, 42, 0.35);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        overflow: hidden;
    }
    .hero-container::after {
        content: "";
        position: absolute;
        top: -50%;
        right: -20%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, rgba(56, 189, 248, 0.15) 0%, transparent 70%);
        border-radius: 50%;
        pointer-events: none;
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        color: #F8FAFC !important;
    }
    .hero-badge {
        background: rgba(56, 189, 248, 0.2);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.4);
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .hero-subtitle {
        color: #94A3B8;
        font-size: 1.05rem;
        margin-top: 0.5rem;
        margin-bottom: 0;
        max-width: 800px;
        line-height: 1.5;
    }

    /* KPI Metrics Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1.2rem;
        margin-bottom: 1.8rem;
    }
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 1.3rem 1.4rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -2px rgba(0, 0, 0, 0.03);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.06);
    }
    .kpi-card.blue { border-top: 4px solid #0284C7; }
    .kpi-card.emerald { border-top: 4px solid #10B981; }
    .kpi-card.amber { border-top: 4px solid #F59E0B; }
    .kpi-card.rose { border-top: 4px solid #EF4444; }

    .kpi-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748B;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 800;
        color: #0F172A;
        margin-top: 0.2rem;
        letter-spacing: -0.02em;
    }
    .kpi-sub {
        font-size: 0.85rem;
        color: #94A3B8;
        margin-top: 0.25rem;
    }

    /* Session Chips */
    .session-chip-active {
        background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%);
        border: 1px solid #86EFAC;
        border-radius: 14px;
        padding: 1rem 1.4rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .session-chip-inactive {
        background: linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 100%);
        border: 1px solid #FECDD3;
        border-radius: 14px;
        padding: 1rem 1.4rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    /* Card Panels */
    .content-panel {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 1.6rem 1.8rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }
    
    .status-pill {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
    }
    .status-pill.success { background: #DCFCE7; color: #166534; }
    .status-pill.in_progress { background: #FEF3C7; color: #92400E; }
    .status-pill.failed { background: #FEE2E2; color: #991B1B; }
    .status-pill.pending { background: #F1F5F9; color: #475569; }

    /* Buttons & Controls */
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        padding: 0.55rem 1.25rem;
        transition: all 0.2s ease;
        border: 1px solid transparent;
    }
    .stDownloadButton>button {
        border-radius: 10px;
        font-weight: 600;
        padding: 0.55rem 1.25rem;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Initialize Persistence & Session State
# -----------------------------------------------------------------------------
repo = UploadRepository()

if "session_info" not in st.session_state:
    st.session_state["session_info"] = {"checked": False, "logged_in": False}

# Auto-check portal session on load if not yet validated
if not st.session_state["session_info"].get("checked"):
    try:
        status_res = check_session_status(headless=True)
        st.session_state["session_info"] = {
            "checked": True,
            "logged_in": status_res.get("logged_in", False),
            "user": status_res.get("user", ""),
            "school": status_res.get("school", ""),
            "role": status_res.get("role", "")
        }
    except Exception:
        st.session_state["session_info"] = {"checked": True, "logged_in": False}

session_info = st.session_state["session_info"]

# -----------------------------------------------------------------------------
# Sidebar Navigation & Settings
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Workspace Settings")
    stage_option = st.selectbox(
        "Default HPC Stage",
        ["Preparatory (Grades 3-5)", "Middle (Grades 6-8)"],
        index=0,
        help="Select default stage. Note: Uploading an Excel workbook will also auto-detect the stage based on grades."
    )
    current_stage = "Preparatory" if "Preparatory" in stage_option else "Middle"

    headless_mode = st.checkbox("Headless Browser Execution", value=False, help="Run browser in background without opening visible windows.")

    st.markdown("---")
    st.markdown("### 🔐 PARAKH Portal Session")

    if session_info.get("logged_in"):
        u_name = session_info.get("user", "Teacher")
        u_school = session_info.get("school", "Assigned School")
        u_role = session_info.get("role", "TEACHER")
        st.success(f"🟢 **Session Active**  \n👤 **{u_name}**  \n🏫 {u_school}  \n🏷️ `{u_role}`")
    else:
        st.warning("🔴 **Session Inactive**  \nAuthenticate with your PARAKH teacher credentials to fetch rosters or automate upload.")

    col_side_1, col_side_2 = st.columns(2)
    with col_side_1:
        if st.button("🔑 Login", key="side_login_btn", use_container_width=True, help="Opens browser window to input username, password & OTP"):
            with st.spinner("Launching PARAKH login window..."):
                res = start_interactive_session()
                if res.get("success"):
                    st.session_state["session_info"] = {
                        "checked": True,
                        "logged_in": True,
                        "user": res.get("user"),
                        "school": res.get("school"),
                        "role": res.get("role")
                    }
                    st.toast(f"Welcome, {res.get('user')}! Session active.", icon="🎉")
                    st.rerun()
                else:
                    st.error(res.get("error", "Login timed out or window closed."))
    with col_side_2:
        if st.button("🚪 Logout", key="side_logout_btn", use_container_width=True, help="Terminates active session and clears cached cookies"):
            end_session()
            st.session_state["session_info"] = {"checked": True, "logged_in": False}
            st.toast("Session ended successfully.", icon="👋")
            st.rerun()

    if st.button("🔄 Check Session Health", key="side_verify_btn", use_container_width=True):
        with st.spinner("Checking portal connectivity..."):
            status_res = check_session_status(headless=True)
            st.session_state["session_info"] = {
                "checked": True,
                "logged_in": status_res.get("logged_in", False),
                "user": status_res.get("user", ""),
                "school": status_res.get("school", ""),
                "role": status_res.get("role", "")
            }
            st.rerun()

    st.markdown("---")
    st.markdown("### 🌐 Global Part-B Activity")
    
    # Load global activities config
    global_acts_file = ROOT / "config" / "global_activities.json"
    global_acts = []
    if global_acts_file.exists():
        try:
            ga_data = json.loads(global_acts_file.read_text(encoding="utf-8"))
            if isinstance(ga_data, list):
                global_acts = ga_data
        except Exception:
            pass

    selected_activity = "Activity 5 (L1CG 1 C-1.2)"
    if global_acts:
        act_names = [a.get("name") or a.get("code") or f"Activity {i+1}" for i, a in enumerate(global_acts)]
        default_idx = 0
        for i, n in enumerate(act_names):
            if "c-1.2" in n.lower() or "c1.2" in n.lower():
                default_idx = i
                break
        selected_activity = st.selectbox(
            "Selected Integrated Activity",
            act_names,
            index=default_idx,
            help="Integrated all-subject activity. Supports adding all 7 learning subjects under one umbrella."
        )
        st.caption(f"📁 Covers: *Language (R1/R2), Math, World Around Us, Arts, PE, Other*")

# -----------------------------------------------------------------------------
# Top Hero Banner
# -----------------------------------------------------------------------------
st.markdown("""
<div class="hero-container">
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
        <div>
            <div class="hero-title">
                🎓 Holistic Progress Card (HPC) Automation
                <span class="hero-badge">Enterprise v2.4</span>
            </div>
            <p class="hero-subtitle">
                Official PARAKH NCERT Portal companion. Synchronize student rosters, grade competencies offline with multi-month attendance in Excel, and batch submit verified evaluations.
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# High-Level KPI Summary Cards
# -----------------------------------------------------------------------------
all_logs = repo.get_all_logs()
total_records = len(all_logs)
success_records = sum(1 for l in all_logs if l.status == UploadState.SUCCESS)
in_progress_records = sum(1 for l in all_logs if l.status == UploadState.IN_PROGRESS)
failed_records = sum(1 for l in all_logs if l.status == UploadState.FAILED)

completion_rate = int((success_records / total_records * 100)) if total_records > 0 else 0

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card blue">
        <div class="kpi-label">Registered Students</div>
        <div class="kpi-value">{total_records}</div>
        <div class="kpi-sub">Total records in local repository</div>
    </div>
    <div class="kpi-card emerald">
        <div class="kpi-label">Submitted & Verified</div>
        <div class="kpi-value" style="color: #059669;">{success_records}</div>
        <div class="kpi-sub">Completed on official PARAKH portal</div>
    </div>
    <div class="kpi-card amber">
        <div class="kpi-label">In Progress / Staged</div>
        <div class="kpi-value" style="color: #D97706;">{in_progress_records}</div>
        <div class="kpi-sub">Pending automated submission</div>
    </div>
    <div class="kpi-card rose">
        <div class="kpi-label">Needs Attention</div>
        <div class="kpi-value" style="color: #DC2626;">{failed_records}</div>
        <div class="kpi-sub">Validation issues or connection drops</div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Main Functional Navigation Tabs
# -----------------------------------------------------------------------------
tab_fetch, tab_upload, tab_history, tab_diagnostics = st.tabs([
    "📥 1. Student Roster Sync",
    "📤 2. Validate & Batch Upload",
    "📊 3. Audit & Submission Evidence",
    "🛠️ 4. Portal Diagnostic & Tools"
])

# =============================================================================
# TAB 1: Roster Synchronization (Fetch Students)
# =============================================================================
with tab_fetch:
    st.subheader(f"Step 1: Download {current_stage} Student Roster from PARAKH")
    st.write("Connects to your active teacher session, pulls your assigned class roster, and builds a pre-filled Excel template.")

    # Portal session status ribbon
    if session_info.get("logged_in"):
        u_name = session_info.get("user", "Teacher")
        u_school = session_info.get("school", "")
        school_str = f" · 🏫 <b>{u_school}</b>" if u_school else ""
        st.markdown(f"""
        <div class="session-chip-active">
            <div>
                <span style="font-size: 1rem; font-weight: 700; color: #166534;">🟢 Teacher Portal Session Active</span>
                <div style="color: #15803D; font-size: 0.9rem; margin-top: 0.2rem;">
                    👤 <b>{u_name}</b>{school_str} · 🏷️ Role: <b>{session_info.get('role', 'TEACHER')}</b>
                </div>
            </div>
            <div>
                <span style="font-size: 0.85rem; background: #BBF7D0; color: #14532D; padding: 0.35rem 0.75rem; border-radius: 8px; font-weight: 600;">Connected to PARAKH</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="session-chip-inactive">
            <div>
                <span style="font-size: 1rem; font-weight: 700; color: #991B1B;">🔴 No Active Teacher Session</span>
                <div style="color: #B91C1C; font-size: 0.9rem; margin-top: 0.2rem;">
                    Please log in via the sidebar button or click below to launch the PARAKH portal window.
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns([2.5, 1.2, 1.2])
    with col_f1:
        fetch_btn = st.button("🚀 Fetch Student Roster from Portal", type="primary", use_container_width=True)
    with col_f2:
        clear_roster_btn = st.button("🗑️ Clear Local Roster", use_container_width=True, help="Removes locally cached student JSON and Excel")
    with col_f3:
        refresh_acts_btn = st.button("🔄 Sync Activities", use_container_width=True, help="Downloads latest activity bank from PARAKH")

    excel_file_path = ROOT / "data" / f"hpc_{current_stage.lower()}_students_filled.xlsx"
    backup_json_path = ROOT / "data" / f"fetched_students_{current_stage.lower()}.json"

    if clear_roster_btn:
        if excel_file_path.exists():
            excel_file_path.unlink()
        if backup_json_path.exists():
            backup_json_path.unlink()
        st.session_state.pop("fetched_students", None)
        st.toast("Local roster cache cleared.", icon="🧹")
        st.rerun()

    if refresh_acts_btn:
        with st.spinner("Synchronizing activity bank from portal..."):
            try:
                acts = fetch_global_activities_from_portal(headless=headless_mode)
                if acts:
                    st.success(f"Loaded {len(acts)} activities from portal. Reload to view in dropdown.")
                else:
                    st.warning("No activities returned. Ensure you are logged in.")
            except Exception as e:
                st.error(f"Sync failed: {e}")

    if fetch_btn:
        with st.spinner(f"Extracting {current_stage} student roster from PARAKH portal..."):
            try:
                students = fetch_students_from_portal(stage=current_stage, headless=headless_mode)
                if students:
                    st.toast(f"Successfully fetched {len(students)} students!", icon="🎉")
                    out_path = generate_prepopulated_excel(students, stage=current_stage, activity_name=selected_activity)
                    st.session_state["fetched_students"] = students
                else:
                    st.warning("No students returned from the portal. Verify your assigned classes on PARAKH.")
            except Exception as exc:
                st.error(f"Error fetching students: {exc}")

    # Preview Table & Download Button
    if backup_json_path.exists():
        st.markdown("---")
        st.subheader("📋 Class Roster Preview")
        try:
            with open(backup_json_path, "r", encoding="utf-8") as f:
                s_data = json.load(f)
            df_preview = pd.DataFrame(s_data)[["admission_number", "student_name", "gender", "grade", "section", "status"]]
            df_preview.columns = ["Admission No", "Student Name", "Gender", "Grade", "Section", "Portal Status"]
            st.dataframe(df_preview, use_container_width=True, height=260)
        except Exception:
            pass

        if excel_file_path.exists():
            with open(excel_file_path, "rb") as f:
                excel_bytes = f.read()

            st.download_button(
                label=f"⬇️ Download Pre-Populated Excel ({excel_file_path.name})",
                data=excel_bytes,
                file_name=excel_file_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

# =============================================================================
# TAB 2: Validate & Upload
# =============================================================================
with tab_upload:
    st.subheader("Step 2: Inspect, Validate & Upload Graded Excel")
    st.write("Upload your completed Excel workbook. The engine will inspect all records against PARAKH portal rules and character limits before submission.")

    uploaded_file = st.file_uploader(
        "Upload Filled HPC Workbook (.xlsx)",
        type=["xlsx"],
        help="Upload the filled student workbook (e.g., hpc_preparatory_students_filled.xlsx or hpc_middle_students_filled.xlsx)"
    )

    if uploaded_file is not None:
        temp_path = ROOT / "data" / f"temp_upload_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        try:
            records = import_preparatory_workbook(temp_path)
            
            # Smart Auto-Stage Detection from Records
            detected_stage = current_stage
            if records:
                sample_grade = str(records[0].get("data", {}).get("grade", "")).lower()
                if any(g in sample_grade for g in ("6", "7", "8", "middle")):
                    detected_stage = "Middle"
                elif any(g in sample_grade for g in ("3", "4", "5", "prep")):
                    detected_stage = "Preparatory"

            st.markdown(f"""
            <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 12px; padding: 0.85rem 1.25rem; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <b>Loaded:</b> <code>{len(records)}</code> student records from <b>{uploaded_file.name}</b>
                    <span style="margin-left: 0.8rem; background: #E0F2FE; color: #0369A1; padding: 0.25rem 0.65rem; border-radius: 6px; font-size: 0.82rem; font-weight: 700;">
                        🎯 Auto-Detected Stage: {detected_stage}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if records:
                sample_data = records[0].get("data", {})
                w_days = sample_data.get("working_days", "271")
                max_marks = sample_data.get("max_summative_marks", "33")
                st.caption(f"🌿 **Seeder Parameters (Sheet 1)**: Total 12-Month Working Days = `{w_days}` days | Max Summative Marks = `{max_marks}`")

            # Run Comprehensive Validation
            report = validate_workbook_records(records)

            if report.is_valid:
                st.markdown("""
                <div style="background: #ECFDF5; border: 1px solid #10B981; border-radius: 12px; padding: 1rem 1.4rem; margin-bottom: 1.2rem;">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <span style="font-size: 1.4rem;">✅</span>
                        <div>
                            <span style="font-size: 1.05rem; font-weight: 700; color: #065F46;">Validation Passed (0 Errors)</span>
                            <div style="color: #047857; font-size: 0.9rem; margin-top: 0.15rem;">
                                All student records, grades (3-8), character length limits, and ratings comply with PARAKH portal requirements.
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #FEF2F2; border: 1px solid #EF4444; border-radius: 12px; padding: 1rem 1.4rem; margin-bottom: 1.2rem;">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <span style="font-size: 1.4rem;">❌</span>
                        <div>
                            <span style="font-size: 1.05rem; font-weight: 700; color: #991B1B;">Validation Failed: {len(report.errors)} Error(s)</span>
                            <div style="color: #B91C1C; font-size: 0.9rem; margin-top: 0.15rem;">
                                Please review and resolve the errors below in Excel before initiating portal upload.
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                err_df = pd.DataFrame([{"Row": e.row, "Field": e.field, "Message": e.message} for e in report.errors])
                st.dataframe(err_df, use_container_width=True)

            if report.warnings:
                with st.expander(f"⚠️ {len(report.warnings)} Warning(s) Detected (Non-blocking)"):
                    warn_df = pd.DataFrame([{"Row": w.row, "Field": w.field, "Message": w.message} for w in report.warnings])
                    st.dataframe(warn_df, use_container_width=True)

            # Upload Trigger
            st.markdown("---")
            can_upload = report.is_valid
            start_upload_btn = st.button(
                f"🚀 Start Automated Upload ({len(records)} Students · {detected_stage} Stage)",
                type="primary",
                disabled=not can_upload,
                use_container_width=True
            )

            if start_upload_btn:
                progress_bar = st.progress(0)
                status_box = st.empty()
                status_box.info(f"Connecting to PARAKH portal in {'headless' if headless_mode else 'visible'} mode...")

                with st.spinner("Automating multi-step evaluation submissions..."):
                    import importlib
                    importlib.reload(portal.uploader)
                    results = portal.uploader.upload_batch_students(records, headless=headless_mode, stage=detected_stage)
                    progress_bar.progress(100)

                st.balloons()
                st.success(f"🎉 Upload Batch Finished! Success: {results['success']} students | Failed: {results['failed']}")

        except Exception as e:
            st.error(f"Failed to process workbook: {e}")

# =============================================================================
# TAB 3: Audit & Submission Evidence
# =============================================================================
with tab_history:
    st.subheader("Step 3: Verification Audit & Screenshot Evidence")
    st.write("Complete audit trail of all student upload transactions with official PARAKH screenshot evidence.")

    logs = repo.get_all_logs()

    if not logs:
        st.info("No upload history recorded yet. Upload student workbooks in Tab 2 to populate audit logs.")
    else:
        log_rows = []
        for l in logs:
            log_rows.append({
                "Admission No": l.admission_number,
                "Student Name": l.student_name,
                "Stage": l.stage,
                "Status": l.status.value,
                "Attempts": l.attempt_count,
                "Last Attempt": str(l.last_attempt_at)[:19] if l.last_attempt_at else "-",
                "Completed At": str(l.completed_at)[:19] if l.completed_at else "-",
                "Screenshot Evidence": l.screenshot_evidence or "-"
            })
        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, height=350)

    # Screenshot Gallery
    evidence_dir = ROOT / "audit_evidence"
    if evidence_dir.exists():
        screenshots = sorted(list(evidence_dir.glob("*.png")), key=lambda p: p.stat().st_mtime, reverse=True)
        if screenshots:
            st.markdown("---")
            st.subheader("📸 Photographic Proof Gallery")
            st.caption("Visual proof of successful completion screens saved directly from the PARAKH portal.")
            
            sel_shot = st.selectbox("Select Evidence Screenshot", [s.name for s in screenshots], index=0)
            if sel_shot:
                shot_path = evidence_dir / sel_shot
                st.image(str(shot_path), caption=f"PARAKH Verification Evidence: {sel_shot}", use_container_width=True)

# =============================================================================
# TAB 4: Portal Diagnostic & System Health
# =============================================================================
with tab_diagnostics:
    st.subheader("System Diagnostics & Utilities")
    st.write("Verify environment health, clean stale browser locks, and test connectivity to PARAKH.")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.markdown("#### 🧹 Zombie Browser Cleanup")
        st.write("Cleans any abandoned Chromium processes or locks preventing new sessions.")
        if st.button("Clean Stale Browser Processes", use_container_width=True):
            cleanup_zombie_browsers()
            st.success("Cleaned all stale browser locks and instances.")

    with col_d2:
        st.markdown("#### 📁 Repository Storage Health")
        db_file = ROOT / "data" / "hpc_automation.db"
        db_size_kb = db_file.stat().st_size // 1024 if db_file.exists() else 0
        st.write(f"- **Database Path:** `{db_file.name}` ({db_size_kb} KB)")
        st.write(f"- **Audit Evidence Folder:** `{len(list(evidence_dir.glob('*.png')) if evidence_dir.exists() else [])}` files")
        st.write(f"- **Portal Endpoint:** `https://hpc.parakh.ncert.gov.in/en`")
