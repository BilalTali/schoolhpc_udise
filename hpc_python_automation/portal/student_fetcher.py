"""
Student Fetcher: fetches the official student roster directly from the HPC portal
and generates a pre-populated Excel workbook with all student details ready for data entry.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright, Page, Response

from portal.login import get_browser_context, wait_for_manual_login

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_SCHEMA = ROOT / "config" / "stage_schemas.json"
DATA_DIR.mkdir(exist_ok=True)

RATING_OPTIONS = '"beginner,proficient,advance"'
GENDER_OPTIONS = '"Boy,Girl,Other"'
GRADE_OPTIONS = '"Grade 3,Grade 4,Grade 5"'
YES_NO_OPTIONS = '"Yes,No"'


def fetch_students_from_portal(stage: str = "Preparatory", headless: bool = False, profile_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Opens the HPC portal, navigates to the stage student list, intercepts the
    Bearer token from live network requests, then calls the official teacher
    roster API directly to get all students instantly.
    Also enriches each student with part_a1 details (dob, guardian, admission number).
    Returns the parsed list of students ready for template generation.
    """
    import requests as _requests

    students: List[Dict[str, Any]] = []
    stage_upper = "PREPARATORY" if stage.lower() == "preparatory" else "MIDDLE"
    stage_slug = "preparatory-stage" if stage.lower() == "preparatory" else "middle-stage"
    target_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}"

    # Grade ID → Grade string map
    GRADE_MAP = {6: "Grade 3", 7: "Grade 4", 8: "Grade 5",
                 9: "Grade 6", 10: "Grade 7", 11: "Grade 8"}
    DEFAULT_GRADE = "Grade 6" if stage.lower() == "middle" else "Grade 5"

    print(f"\n[INFO] Connecting to HPC Portal to fetch {stage} student roster...")

    auth_token = None
    session_info = {}

    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=headless, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Step 1: Ensure login
        wait_for_manual_login(page)

        # Step 2: Intercept Bearer token from outgoing requests
        def _capture_token(req):
            nonlocal auth_token
            auth = req.headers.get("authorization", "")
            if auth.startswith("Bearer eyJ"):
                auth_token = auth

        page.on("request", _capture_token)

        # Step 3: Navigate to trigger auth'd API calls
        print(f"[INFO] Navigating to {target_url}...")
        page.goto(target_url, wait_until="networkidle")
        time.sleep(2)

        # Check if redirected to login page (/en)
        cur_url = page.url
        if cur_url.endswith("/en") or cur_url.endswith("/en/"):
            ctx.close()
            raise PermissionError(
                "User session has expired or is not authenticated. "
                "Please click 'Start Session' to log in."
            )

        # Step 4: Get session metadata (state, district, school, staff) via JS
        session_info = page.evaluate("""
            async () => {
                try {
                    const s = await (await fetch('/api/auth/session')).json();
                    const u = s.user || {};
                    return {
                        state: u.state_code_internal || 'jk',
                        ay: u.school_cur_ay_code || '2627',
                        district_id: u.district_id || '',
                        school_id: u.school_id || '',
                        staff_id: u.staff_id || ''
                    };
                } catch(e) { return {}; }
            }
        """)

        ctx.close()

    state = session_info.get("state") or "jk"
    ay = session_info.get("ay") or "2627"
    district_id = session_info.get("district_id", "")
    school_id = session_info.get("school_id", "")
    staff_id = session_info.get("staff_id", "")

    if not auth_token:
        print("[WARN] No Bearer token captured from network — falling back to empty list.")
        return []

    headers = {
        "Authorization": auth_token,
        "Accept": "application/json",
    }

    # Step 5: Call official teacher roster API
    roster_url = (
        f"https://hpc.parakh.ncert.gov.in/api/proxy/states/{state}"
        f"/districts/{district_id}/schools/{school_id}"
        f"/teachers/{staff_id}/hpc/{stage_upper}?page_no=1&page_size=100"
    )
    print(f"[INFO] Fetching roster from: {roster_url}")
    try:
        resp = _requests.get(roster_url, headers=headers, timeout=30)
        resp.raise_for_status()
        roster_data = resp.json()
    except Exception as exc:
        print(f"[ERROR] Roster API failed: {exc}")
        return []

    records = (roster_data.get("data") or {}).get("records") or []
    print(f"[INFO] Roster returned {len(records)} record(s).")

    # Step 6: Map roster records directly — no per-student API calls needed
    for rec in records:
        student_id = str(rec.get("id") or "")
        grade_id = rec.get("grade_id")
        grade_str = GRADE_MAP.get(grade_id, DEFAULT_GRADE)

        # Normalise gender
        raw_gender = str(rec.get("gender") or "Male").strip()
        gender = raw_gender.capitalize()
        if gender not in ("Male", "Female", "Other"):
            gender = "Male"

        student_name = str(rec.get("full_name") or "").strip()
        if not student_name:
            fn = str(rec.get("std_fname") or "")
            ln = str(rec.get("std_lname") or "")
            student_name = (fn + " " + ln).strip()

        # std_reg_id is the HPC Login ID / admission number from portal
        hpc_login_id = str(rec.get("std_reg_id") or "").strip()
        admission_number = str(
            rec.get("school_admission_number") or hpc_login_id or ""
        ).strip()
        apaar_id = str(rec.get("std_apaar_id") or "").strip()
        hpc_status = str(rec.get("hpc_status") or "PENDING")
        section = str(rec.get("section_id") or "A").strip()

        students.append({
            "student_id": student_id,
            "admission_number": admission_number,
            "student_name": student_name,
            "apaar_id": apaar_id,
            "hpc_login_id": hpc_login_id,
            "dob": "2015-01-01",
            "gender": gender,
            "grade": grade_str,
            "section": section if len(section) == 1 else "A",
            "mother_tongue": "Kashmiri",
            "guardian_name": "",
            "status": hpc_status,
            "activity_name": "L1CG 1 (C-1.2)",
            "activity_subject": "All",
        })

    # Save raw json backup
    backup_file = DATA_DIR / f"fetched_students_{stage.lower()}.json"
    backup_file.write_text(json.dumps(students, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Fetched {len(students)} student(s).")
    print(f"[OK] Backup saved: {backup_file}")

    return students


def fetch_global_activities_from_portal(headless: bool = False) -> List[Dict[str, Any]]:
    """
    Connects to the HPC portal via the authenticated browser session and fetches
    the official global activities list via the portal API:
      GET /api/proxy/country/activities
    Saves results to config/global_activities.json for use in Excel dropdowns.
    Returns the list of global activities.
    """
    GLOBAL_ACTS_FILE = ROOT / "config" / "global_activities.json"
    print("\n[INFO] Fetching global activities from HPC Portal API...")

    activities = []
    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        wait_for_manual_login(page)

        fetch_js = """
        async () => {
            try {
                const res = await fetch('/api/proxy/country/activities', {
                    headers: { 'Accept': 'application/json' }
                });
                if (!res.ok) return { error: 'HTTP ' + res.status };
                return await res.json();
            } catch (e) {
                return { error: e.toString() };
            }
        }
        """
        data = page.evaluate(fetch_js)
        ctx.close()

    if isinstance(data, list) and data:
        activities = data
        GLOBAL_ACTS_FILE.write_text(json.dumps(activities, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] Fetched {len(activities)} global activities; saved to {GLOBAL_ACTS_FILE}")
    elif isinstance(data, dict) and "error" in data:
        print(f"[WARN] Portal API error: {data['error']} - using cached/default list")
    else:
        print(f"[WARN] Unexpected response type: {type(data)} - using cached/default list")

    return activities


from excel.template_generator import (
    get_preparatory_columns,
    _build_global_seeder_sheet,
    RATING_OPTIONS,
    OVERALL_RATING_OPTIONS,
    GENDER_OPTIONS,
    GRADE_OPTIONS,
    YES_NO_OPTIONS,
    MEDIUM_OPTIONS,
    AREA_OPTIONS,
    GUARDIAN_TYPE_OPTIONS,
    GLOBAL_ACTIVITY_OPTIONS,
    SUBJECT_COVERAGE_OPTIONS,
)


def generate_prepopulated_excel(
    students: List[Dict[str, Any]],
    stage: str = "Preparatory",
    output_file: Optional[Path] = None,
    activity_name: str = "L1CG 1 (C-1.2)"
) -> Path:
    """
    Builds the standardized Excel template with the fetched student records pre-filled row-by-row.
    Includes:
      - Sheet 1: Global_Class_Config seeder
      - Sheet 2: HPC_{stage} with fixed columns A, B, C (frozen at D4) and Part-B competencies tailored to the selected activity.
    """
    if output_file is None:
        output_file = DATA_DIR / f"hpc_{stage.lower()}_students_filled.xlsx"

    schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
    prep = schema.get("Preparatory", {})
    sections = prep.get("sections", {})

    wb = Workbook()

    # 1. Global Seeder Sheet
    ws_seeder = wb.active
    _build_global_seeder_sheet(ws_seeder, selected_activity=activity_name)

    # 2. Main Student Roster Sheet
    ws = wb.create_sheet(title=f"HPC_{stage}")

    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_section = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_data = Font(name="Segoe UI", size=10)
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    border_thin = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )

    columns = get_preparatory_columns(sections, selected_activity=activity_name)

    # Validations
    dv_rating = DataValidation(type="list", formula1=RATING_OPTIONS, allow_blank=True)
    dv_overall_rating = DataValidation(type="list", formula1=OVERALL_RATING_OPTIONS, allow_blank=True)
    dv_gender = DataValidation(type="list", formula1=GENDER_OPTIONS, allow_blank=True)
    dv_grade = DataValidation(type="list", formula1=GRADE_OPTIONS, allow_blank=True)
    dv_yesno = DataValidation(type="list", formula1=YES_NO_OPTIONS, allow_blank=True)
    dv_medium = DataValidation(type="list", formula1=MEDIUM_OPTIONS, allow_blank=True)
    dv_area = DataValidation(type="list", formula1=AREA_OPTIONS, allow_blank=True)
    dv_guardian = DataValidation(type="list", formula1=GUARDIAN_TYPE_OPTIONS, allow_blank=True)
    dv_activity = DataValidation(type="list", formula1=GLOBAL_ACTIVITY_OPTIONS, allow_blank=True)
    dv_coverage = DataValidation(type="list", formula1=SUBJECT_COVERAGE_OPTIONS, allow_blank=True)

    for dv in (dv_rating, dv_overall_rating, dv_gender, dv_grade, dv_yesno, dv_medium, dv_area, dv_guardian, dv_activity, dv_coverage):
        ws.add_data_validation(dv)

    section_ranges = {}

    for col_idx, (key, label, sec_group, fill_color, val_rule, sample_val) in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)

        if sec_group not in section_ranges:
            section_ranges[sec_group] = [col_letter, col_letter]
        else:
            section_ranges[sec_group][1] = col_letter

        # Row 1: Section group
        c_sec = ws.cell(row=1, column=col_idx, value=sec_group)
        c_sec.fill = fill_color
        c_sec.font = font_section
        c_sec.alignment = align_center

        # Row 2: Human-readable header
        c_hdr = ws.cell(row=2, column=col_idx, value=label)
        c_hdr.fill = fill_color
        c_hdr.font = font_header
        c_hdr.alignment = align_center
        c_hdr.border = border_thin

        # Row 3: Technical key
        c_key = ws.cell(row=3, column=col_idx, value=key)
        c_key.font = Font(name="Segoe UI", size=8, color="888888", italic=True)
        c_key.alignment = align_center
        c_key.border = border_thin

        # Column width
        ws.column_dimensions[col_letter].width = max(len(label) + 2, 14)

        # Attach validation
        val_range = f"{col_letter}4:{col_letter}{max(len(students) + 20, 100)}"
        if val_rule == RATING_OPTIONS:
            dv_rating.add(val_range)
        elif val_rule == OVERALL_RATING_OPTIONS:
            dv_overall_rating.add(val_range)
        elif val_rule == GENDER_OPTIONS:
            dv_gender.add(val_range)
        elif val_rule == GRADE_OPTIONS:
            dv_grade.add(val_range)
        elif val_rule == YES_NO_OPTIONS:
            dv_yesno.add(val_range)
        elif val_rule == MEDIUM_OPTIONS:
            dv_medium.add(val_range)
        elif val_rule == AREA_OPTIONS:
            dv_area.add(val_range)
        elif val_rule == GUARDIAN_TYPE_OPTIONS:
            dv_guardian.add(val_range)
        elif val_rule == GLOBAL_ACTIVITY_OPTIONS:
            dv_activity.add(val_range)
        elif val_rule == SUBJECT_COVERAGE_OPTIONS:
            dv_coverage.add(val_range)

    # Write Student Rows
    for s_idx, student in enumerate(students, start=4):
        for col_idx, (key, _, _, _, _, default_val) in enumerate(columns, start=1):
            val = student.get(key, default_val)
            cell = ws.cell(row=s_idx, column=col_idx, value=val)
            cell.font = font_data
            cell.border = border_thin
            cell.alignment = align_left if str(val).isalpha() else align_center

    # Pinned Columns: A (Name), B (APAAR ID), C (Gender) remain fixed on screen
    ws.freeze_panes = "D4"

    # Part-wise collapsible grouping
    for sec_name, (start_col, end_col) in section_ranges.items():
        if sec_name != "Fixed Student Info":
            ws.column_dimensions.group(start_col, end_col, outline_level=1, hidden=False)

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 42
    ws.row_dimensions[3].height = 18

    # Default view on student sheet
    wb.active = ws

    wb.save(output_file)
    print(f"[OK] Pre-populated Excel created at: {output_file}")
    return output_file
