"""
Template generator: creates the complete, high-fidelity HPC Preparatory Stage Excel template
with optimized column architecture:
  1. Fixed Columns (A, B, C): Student Name, APAAR ID, Gender (frozen on screen at D4).
  2. Part-wise Collapsible Groups: Each part can be expanded or collapsed with one click.
  3. Global Class Seeder Sheet ('Global_Class_Config'): Seeds working days (APR..MAR),
     maximum marks (33), and class metadata globally to minimize redundant columns in student rows.
  4. Two Data Sheets:
     - 'HPC_Preparatory_Blank': Blank template ready for teacher entry.
     - 'Sample_Filled_Student': Exemplary, professional sample covering all fields.
"""
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
CONFIG_SCHEMA = ROOT / "config" / "stage_schemas.json"
GLOBAL_ACTIVITIES_FILE = ROOT / "config" / "global_activities.json"
DATA_DIR = ROOT / "data"
TEMPLATE_OUT = DATA_DIR / "hpc_preparatory_template.xlsx"

# Dropdown list choices
RATING_OPTIONS = '"beginner,proficient,advance"'
OVERALL_RATING_OPTIONS = '"BEGINNER,PROFICIENT,ADVANCE"'
GENDER_OPTIONS = '"Male,Female,Other"'
GRADE_OPTIONS = '"Grade 3,Grade 4,Grade 5"'
YES_NO_OPTIONS = '"Yes,No"'
MEDIUM_OPTIONS = '"English,Hindi,Urdu,Kashmiri,Punjabi,Dogri,Other"'
AREA_OPTIONS = '"Rural,Urban"'
GUARDIAN_TYPE_OPTIONS = '"Mother,Father,Guardian (Other than Parents)"'
SUBJECT_COVERAGE_OPTIONS = '"All,Language Education (R1),Language Education (R2),Mathematics,The World Around Us,Art Education (AE),Physical Education and Well-being,Other Learning Activities"'


def _build_global_activity_options() -> str:
    """
    Builds the Excel dropdown list string for global activities.
    Loads from config/global_activities.json if available; falls back to built-in list.
    Always puts Activity 5 (L1CG 1, C-1.2) first as the recommended integrated activity.
    """
    default_acts = [
        "L1CG 1 (C-1.2)",      # Activity 5 - integrated all-subject (default)
        "L1CG 1 (C-1.1)",
        "TWCG 1 (C-1.2)",
        "MCG 1 (C-1.1)",
        "AEC 1 (C-1.1)",
        "P1CG 1 (C-1.1)",
    ]
    if GLOBAL_ACTIVITIES_FILE.exists():
        try:
            acts = json.loads(GLOBAL_ACTIVITIES_FILE.read_text(encoding="utf-8"))
            if isinstance(acts, list) and acts:
                names = []
                for a in acts:
                    n = (a.get("name") or a.get("code") or "").strip()
                    if n and n not in names:
                        names.append(n)
                if names:
                    return '"' + ",".join(names) + '"'
        except Exception:
            pass
    return '"' + ",".join(default_acts) + '"'


GLOBAL_ACTIVITY_OPTIONS = _build_global_activity_options()

# Default Global Seeder Settings
DEFAULT_GLOBAL_SEEDER = [
    ("academic_year", "Academic Year", "2024-25", "Class academic cycle"),
    ("grade", "Default Class Grade", "Grade 5", "Grade 3, Grade 4, or Grade 5"),
    ("section", "Default Section", "A", "Class section"),
    ("medium_of_instruction", "Medium of Instruction", "English", "Primary language of instruction"),
    ("rural_urban", "School Location", "Rural", "Rural or Urban"),
    ("apr_working_days", "APR: Working Days", "22", "Monthly school working days"),
    ("may_working_days", "MAY: Working Days", "23", "Monthly school working days"),
    ("jun_working_days", "JUNE: Working Days", "23", "Monthly school working days"),
    ("jul_working_days", "JULY: Working Days", "22", "Monthly school working days"),
    ("aug_working_days", "AUG: Working Days", "23", "Monthly school working days"),
    ("sep_working_days", "SEP: Working Days", "22", "Monthly school working days"),
    ("oct_working_days", "OCT: Working Days", "23", "Monthly school working days"),
    ("nov_working_days", "NOV: Working Days", "23", "Monthly school working days"),
    ("dec_working_days", "DEC: Working Days", "22", "Monthly school working days"),
    ("jan_working_days", "JAN: Working Days", "23", "Monthly school working days"),
    ("feb_working_days", "FEB: Working Days", "22", "Monthly school working days"),
    ("mar_working_days", "MAR: Working Days", "23", "Monthly school working days"),
    ("max_summative_marks", "Max Marks per Subject (Summative)", "33", "NCERT benchmark summative maximum marks"),
    # Activity 5 (L1CG 1, C-1.2): Integrated All-Subject Activity (default - covers all 7 subjects)
    ("activity_name", "Part-B Global Activity (Activity 5)", "L1CG 1 (C-1.2)", "Select from dropdown - Activity 5: L1CG 1 (C-1.2) is the integrated all-subject activity"),
    ("activity_subject", "Part-B Subject Coverage", "All", "'All' adds all 7 subjects under this single activity; or pick a specific subject"),
    ("credits_earned", "HPC Credits Benchmark", "40", "Total credits earned through HPC"),
    ("declaration_agreed", "Declaration Certified", "Yes", "Teacher validation declaration"),
]


def get_competencies_for_activity(activity_name: str, part_b_fields: list) -> list:
    """Returns only the competencies belonging to the specified global activity."""
    comps = [f for f in part_b_fields if f.get("key", "").startswith("comp_")]
    act_clean = (activity_name or "").strip()
    if act_clean.upper() == "ALL":
        return comps

    matched = []
    if "c-1.1" in act_clean.lower() or "c1.1" in act_clean.lower():
        if "l1" in act_clean.lower():
            # L1CG 1 (C-1.1) - Language 1 Oral presentation & fluency
            matched = [c for c in comps if any(x in c["key"] for x in ("L1C1_1", "L1C1_2", "L1C1_3"))]
        elif "mc" in act_clean.lower():
            # MCG 1 (C-1.1) - Mathematics & Movement
            matched = [c for c in comps if "MC1" in c["key"] or "DMC1" in c["key"]]
        elif "aec" in act_clean.lower() or "art" in act_clean.lower():
            # AEC 1 (C-1.1) - Art Education Visual Arts
            matched = [c for c in comps if any(x in c["key"] for x in ("AEC1", "VAC1"))]
        elif "p1" in act_clean.lower() or "pe" in act_clean.lower():
            # P1CG 1 (C-1.1) - Physical Education Movement
            matched = [c for c in comps if "P1C1" in c["key"]]
    elif "c-1.2" in act_clean.lower() or "c1.2" in act_clean.lower():
        if "l1" in act_clean.lower():
            # L1CG 1 (C-1.2) - Integrated All-Subject Activity
            matched = [c for c in comps if any(x in c["key"] for x in ("L1C1_2", "L1C2_1", "L1C2_2"))]
        elif "tw" in act_clean.lower() or "world" in act_clean.lower():
            # TWCG 1 (C-1.2) - The World Around Us Natural Systems
            matched = [c for c in comps if "TWC1" in c["key"]]

    if not matched:
        matched = comps[:4]
    return matched


def get_preparatory_columns(sections: dict, selected_activity: str = "L1CG 1 (C-1.2)") -> list:
    """
    Builds the master column specification for Preparatory Stage tailored to the selected Activity.
    Pinned columns: Student Name (A), School Admission Number (B), Grade (C).
    Only the specific competencies for the selected activity are included, keeping Part-B compact and clean.
    """
    fill_fixed = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")      # Slate (Pinned)
    fill_info = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")       # Dark Blue
    fill_attend = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")     # Teal
    fill_interest = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")   # Amber
    fill_a2 = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")         # Purple
    fill_a3 = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")         # Royal Blue
    fill_comp = PatternFill(start_color="4338CA", end_color="4338CA", fill_type="solid")       # Indigo
    fill_feedback = PatternFill(start_color="BE185D", end_color="BE185D", fill_type="solid")   # Pink
    fill_credit = PatternFill(start_color="047857", end_color="047857", fill_type="solid")     # Emerald

    cols = [
        # --- 3 ESSENTIAL PINNED COLUMNS (Student Identifiers) ---
        ("student_name", "Student Name (As per Aadhaar)*", "Fixed Student Info", fill_fixed, None, "Aarav Sharma"),
        ("admission_number", "School Admission Number*", "Fixed Student Info", fill_fixed, None, "558"),
        ("grade", "Grade*", "Fixed Student Info", fill_fixed, GRADE_OPTIONS, "Grade 5"),

        # --- PART A(1): STUDENT PROFILE & REGISTRATION ---
        ("section", "Section", "Part A(1) - Profile", fill_info, None, "A"),
        ("medium_of_instruction", "Medium of Instruction*", "Part A(1) - Profile", fill_info, MEDIUM_OPTIONS, "English"),
        ("rural_urban", "Rural/Urban*", "Part A(1) - Profile", fill_info, AREA_OPTIONS, "Rural"),
        ("mother_tongue", "Mother Tongue*", "Part A(1) - Profile", fill_info, None, "Kashmiri"),
        ("guardian_type", "Mother / Father / Guardian*", "Part A(1) - Profile", fill_info, GUARDIAN_TYPE_OPTIONS, "Mother"),
        ("guardian_name", "Guardian Name*", "Part A(1) - Profile", fill_info, None, "Sunita Sharma"),

        # --- PART A(1): MONTHLY ATTENDANCE (12 Months Present Days - Working Days seeded globally) ---
        ("apr_present_days", "APR: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("may_present_days", "MAY: Present Days", "Part A(1) - Attendance", fill_attend, None, "23"),
        ("jun_present_days", "JUNE: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("jul_present_days", "JULY: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("aug_present_days", "AUG: Present Days", "Part A(1) - Attendance", fill_attend, None, "23"),
        ("sep_present_days", "SEP: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("oct_present_days", "OCT: Present Days", "Part A(1) - Attendance", fill_attend, None, "23"),
        ("nov_present_days", "NOV: Present Days", "Part A(1) - Attendance", fill_attend, None, "21"),
        ("dec_present_days", "DEC: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("jan_present_days", "JAN: Present Days", "Part A(1) - Attendance", fill_attend, None, "23"),
        ("feb_present_days", "FEB: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("mar_present_days", "MAR: Present Days", "Part A(1) - Attendance", fill_attend, None, "22"),
        ("attendance_low_reason", "If attendance is low then reasons thereof", "Part A(1) - Attendance", fill_attend, None, "Short seasonal viral indisposition in November; recovered promptly."),

        # --- PART A(1): INTERESTS (11 CHECKBOXES) ---
        ("interest_reading", "Interest: Reading", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_music", "Interest: Dancing/Singing/Music", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_writing", "Interest: Creative Writing", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_gardening", "Interest: Gardening", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_yoga", "Interest: Yoga", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_art", "Interest: Art", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_craft", "Interest: Craft", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_sports", "Interest: Sports or Games", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_cooking", "Interest: Cooking", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "No"),
        ("interest_chores", "Interest: Participation at home", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "Yes"),
        ("interest_other", "Interest: Other", "Part A(1) - Interests", fill_interest, YES_NO_OPTIONS, "No"),

        # --- PART A(2): STUDENT SELF ASSESSMENT (HAND & ILLUSTRATIONS) ---
        ("hand_finger_1", "Hand (Finger 1): Things About Me", "Part A(2) - Self Assessment", fill_a2, None, "Kindness"),
        ("hand_finger_2", "Hand (Finger 2): Things About Me", "Part A(2) - Self Assessment", fill_a2, None, "Storytelling"),
        ("hand_finger_3", "Hand (Finger 3): Things About Me", "Part A(2) - Self Assessment", fill_a2, None, "Mental Math"),
        ("hand_finger_4", "Hand (Finger 4): Things About Me", "Part A(2) - Self Assessment", fill_a2, None, "Collaborative Learning"),
        ("hand_finger_5", "Hand (Finger 5): Things About Me", "Part A(2) - Self Assessment", fill_a2, None, "Creative Visual Art"),
        ("grow_up_goal", "When I grow up I want to be...", "Part A(2) - Self Assessment", fill_a2, None, "Environmental Scientist to conserve biodiversity"),
        ("admired_person", "One person I admire / like", "Part A(2) - Self Assessment", fill_a2, None, "Dr. A.P.J. Abdul Kalam"),
        ("my_calling_name", "My name is...", "Part A(2) - Self Assessment", fill_a2, None, "Aarav"),
        ("my_age", "I am ... years old", "Part A(2) - Self Assessment", fill_a2, None, "9"),
        ("fav_food", "My Favorite Food", "Part A(2) - Self Assessment", fill_a2, None, "Nutritious homemade lentils, steamed rice, and fresh seasonal orchard fruits"),
        ("fav_games", "My Favorite Games", "Part A(2) - Self Assessment", fill_a2, None, "Badminton, traditional Kho-Kho, and strategic board chess with peers"),
        ("fav_festival", "My Favorite Festival", "Part A(2) - Self Assessment", fill_a2, None, "Diwali and Eid celebrations inspiring harmony, sharing, and joy"),
        ("three_things_1", "3 Things I like to do (1)", "Part A(2) - Self Assessment", fill_a2, None, "Reading illustrated science books"),
        ("three_things_2", "3 Things I like to do (2)", "Part A(2) - Self Assessment", fill_a2, None, "Nurturing school botanical plants"),
        ("three_things_3", "3 Things I like to do (3)", "Part A(2) - Self Assessment", fill_a2, None, "Composing lyrical short poems"),

        # --- PART A(3): PEER & PARENT FEEDBACK ---
        ("peer_feedback", "Peer Feedback (Comments from classmate)", "Part A(3) - Feedback", fill_a3, None, "Very supportive, shares and listens"),
        ("parent_books_magazines", "Home Access: Books and Magazines", "Part A(3) - Feedback", fill_a3, YES_NO_OPTIONS, "Yes"),
        ("parent_learning_corner", "Home Access: Dedicated Study Corner", "Part A(3) - Feedback", fill_a3, YES_NO_OPTIONS, "Yes"),
        ("parent_feedback", "Parent Feedback (Your Child Matters!)", "Part A(3) - Feedback", fill_a3, None, "Demonstrates sincere curiosity, reads independently every evening, and maintains neat study habits."),

        # --- PART B: GLOBAL ACTIVITY SETUP ---
        ("activity_name", "Part-B Activity Name*", "Part B - Activity Setup", fill_comp, GLOBAL_ACTIVITY_OPTIONS, selected_activity),
        ("activity_subject", "Part-B Subject Coverage*", "Part B - Activity Setup", fill_comp, SUBJECT_COVERAGE_OPTIONS, "All"),
        ("part_b_awareness", "Part-B Rating: Awareness*", "Part B - Activity Setup", fill_comp, RATING_OPTIONS, "proficient"),
        ("part_b_sensitivity", "Part-B Rating: Sensitivity*", "Part B - Activity Setup", fill_comp, RATING_OPTIONS, "proficient"),
        ("part_b_creativity", "Part-B Rating: Creativity*", "Part B - Activity Setup", fill_comp, RATING_OPTIONS, "advance"),
        ("part_b_teacher_obs", "Part-B Teacher Observational Notes", "Part B - Activity Setup", fill_comp, None, "Demonstrates keen interest during collaborative investigations. Expresses scientific observations accurately, respects diverse opinions, and connects ecological learning with daily village practices."),
        ("part_b_learning_progress", "Part-B Learning Progress Summary", "Part B - Activity Setup", fill_comp, None, "Transitioned smoothly from guided understanding to self-directed inquiry and creative representation across languages, mathematics, and visual arts."),
    ]

    # --- PART B: ACTIVITY-SPECIFIC COMPETENCIES (Filtered by selected activity) ---
    part_b_fields = sections.get("Part - B", [])
    relevant_comps = get_competencies_for_activity(selected_activity, part_b_fields)
    for idx, f in enumerate(relevant_comps):
        k = f["key"]
        lbl = f["label"]
        sample_rating = "advance" if (idx % 2 == 0) else "proficient"
        cols.append((k, lbl, f"Part-B ({selected_activity})", fill_comp, RATING_OPTIONS, sample_rating))

    # --- PART C & CREDITS ---
    cols.extend([
        ("psls_awareness", "Part C: PSLS Personal-Social Awareness*", "Part C & Credits", fill_feedback, OVERALL_RATING_OPTIONS, "PROFICIENT"),
        ("psls_sensitivity", "Part C: PSLS Sensitivity & Empathy*", "Part C & Credits", fill_feedback, OVERALL_RATING_OPTIONS, "PROFICIENT"),
        ("psls_creativity", "Part C: PSLS Creative & Critical Thinking*", "Part C & Credits", fill_feedback, OVERALL_RATING_OPTIONS, "ADVANCE"),
        ("teacher_overall_rating", "Part C: Overall Teacher Assessment*", "Part C & Credits", fill_feedback, OVERALL_RATING_OPTIONS, "PROFICIENT"),
        ("teacher_remarks", "Part C: Comprehensive Teacher Remarks*", "Part C & Credits", fill_feedback, None, "An articulate, conscientious learner who exhibits exceptional conceptual clarity and reflective thinking across all curriculum areas. Demonstrates commendable teamwork, empathetic communication, and deep ecological awareness. Continuously encourages peers and applies numeracy skillfully. Recommended to pursue advanced creative writing and exploratory science investigations."),
        ("marks_lang1", "Summative Marks: Language 1 (out of 33)", "Part C & Credits", fill_credit, None, "28"),
        ("marks_lang2", "Summative Marks: Language 2 (out of 33)", "Part C & Credits", fill_credit, None, "27"),
        ("marks_math", "Summative Marks: Mathematics (out of 33)", "Part C & Credits", fill_credit, None, "30"),
        ("marks_art", "Summative Marks: Art Education (out of 33)", "Part C & Credits", fill_credit, None, "31"),
        ("marks_phy_ed", "Summative Marks: Physical Education (out of 33)", "Part C & Credits", fill_credit, None, "30"),
        ("credits_earned", "HPC Credits Earned", "Part C & Credits", fill_credit, None, "40"),
        ("declaration_agreed", "Declaration Agreed*", "Part C & Credits", fill_credit, YES_NO_OPTIONS, "Yes"),
    ])

    return cols


def _build_global_seeder_sheet(ws, selected_activity: str = "L1CG 1 (C-1.2)"):
    """Creates the Global Class Configuration & Attendance Seeder sheet."""
    ws.title = "Global_Class_Config"

    font_title = Font(name="Segoe UI", size=13, bold=True, color="1E3A8A")
    font_desc = Font(name="Segoe UI", size=9, italic=True, color="64748B")
    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_key = Font(name="Segoe UI", size=9, color="334155", bold=True)
    font_val = Font(name="Segoe UI", size=10, color="0F172A")
    fill_header = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    border_thin = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    ws.cell(row=1, column=1, value="NCERT PARAKH HPC - Global Class Configuration & Attendance Seeder").font = font_title
    ws.cell(row=2, column=1, value="Values set here automatically seed class-wide defaults (working days, max marks, grade, section) for all students.").font = font_desc

    headers = ["Parameter Key", "Parameter Description", "Configured Global Value", "Notes / Instructions"]
    for c_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=c_idx, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_thin

    for r_idx, (k, label, val, notes) in enumerate(DEFAULT_GLOBAL_SEEDER, start=5):
        if k == "activity_name" and selected_activity:
            val = selected_activity
        c_k = ws.cell(row=r_idx, column=1, value=k)
        c_lbl = ws.cell(row=r_idx, column=2, value=label)
        c_val = ws.cell(row=r_idx, column=3, value=val)
        c_note = ws.cell(row=r_idx, column=4, value=notes)

        for cell in (c_k, c_lbl, c_val, c_note):
            cell.border = border_thin
            if r_idx % 2 == 0:
                cell.fill = fill_alt

        c_k.font = font_key
        c_lbl.font = font_val
        c_val.font = font_title if str(val).isdigit() else font_val
        c_val.alignment = Alignment(horizontal="center" if len(str(val)) <= 10 else "left")
        c_note.font = font_desc

    # Add dropdown validations for activity and subject coverage on Global Seeder
    dv_act_seeder = DataValidation(type="list", formula1=GLOBAL_ACTIVITY_OPTIONS, allow_blank=True)
    dv_cov_seeder = DataValidation(type="list", formula1=SUBJECT_COVERAGE_OPTIONS, allow_blank=True)
    ws.add_data_validation(dv_act_seeder)
    ws.add_data_validation(dv_cov_seeder)
    dv_act_seeder.add("C23")
    dv_cov_seeder.add("C24")

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 38
    ws.column_dimensions["C"].width = 32
    ws.column_dimensions["D"].width = 45
    ws.row_dimensions[4].height = 26


def _apply_sheet_formatting(ws, columns: list, is_sample: bool = False):
    """Applies styling, freeze panes (D4), part-wise collapsible grouping, and dropdown validations."""
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

    # Track sections for part-wise grouping
    section_ranges = {}

    for col_idx, (key, label, sec_group, fill_color, val_rule, sample_val) in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)

        # Track column range per section
        if sec_group not in section_ranges:
            section_ranges[sec_group] = [col_letter, col_letter]
        else:
            section_ranges[sec_group][1] = col_letter

        # Row 1: Section group
        cell_sec = ws.cell(row=1, column=col_idx, value=sec_group)
        cell_sec.fill = fill_color
        cell_sec.font = font_section
        cell_sec.alignment = align_center

        # Row 2: Human-readable header
        cell_hdr = ws.cell(row=2, column=col_idx, value=label)
        cell_hdr.fill = fill_color
        cell_hdr.font = font_header
        cell_hdr.alignment = align_center
        cell_hdr.border = border_thin

        # Row 3: Technical key
        cell_key = ws.cell(row=3, column=col_idx, value=key)
        cell_key.font = Font(name="Segoe UI", size=8, color="888888", italic=True)
        cell_key.alignment = align_center
        cell_key.border = border_thin

        # Row 4: Data (only on sample sheet)
        if is_sample:
            cell_data = ws.cell(row=4, column=col_idx, value=sample_val)
            cell_data.font = font_data
            cell_data.alignment = align_left if str(sample_val).replace(" ", "").isalpha() else align_center
            cell_data.border = border_thin

        # Column width
        col_width = max(len(label) + 2, len(str(sample_val)) + 4 if is_sample else 0, 14)
        ws.column_dimensions[col_letter].width = min(col_width, 42)

        # Attach validations to rows 4..500
        val_range = f"{col_letter}4:{col_letter}500"
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

    # 1. Freeze Panes on D4: Columns A (Name), B (APAAR ID), C (Gender) stay pinned on screen!
    ws.freeze_panes = "D4"

    # 2. Apply Part-wise Collapsible Outlines (excluding fixed columns A, B, C)
    for sec_name, (start_col, end_col) in section_ranges.items():
        if sec_name != "Fixed Student Info":
            ws.column_dimensions.group(start_col, end_col, outline_level=1, hidden=False)

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 42
    ws.row_dimensions[3].height = 18
    if is_sample:
        ws.row_dimensions[4].height = 24


def build_preparatory_template(
    schema_path: Path = CONFIG_SCHEMA,
    output_path: Path = TEMPLATE_OUT,
    selected_activity: str = "L1CG 1 (C-1.2)"
) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    prep = schema.get("Preparatory", {})
    sections = prep.get("sections", {})

    columns = get_preparatory_columns(sections, selected_activity=selected_activity)

    wb = Workbook()

    # 1. Global Seeder Sheet (Tab 1)
    ws_seeder = wb.active
    _build_global_seeder_sheet(ws_seeder, selected_activity=selected_activity)

    # 2. Blank Data Entry Sheet (Tab 2)
    ws_blank = wb.create_sheet(title="HPC_Preparatory_Blank")
    _apply_sheet_formatting(ws_blank, columns, is_sample=False)

    # 3. Fully populated exemplary sample (Tab 3)
    ws_sample = wb.create_sheet(title="Sample_Filled_Student")
    _apply_sheet_formatting(ws_sample, columns, is_sample=True)

    # Default to opening on the Blank entry sheet
    wb.active = ws_blank

    wb.save(output_path)
    return output_path


def main():
    print("Generating Complete Template with Fixed Columns, Part-wise Collapsible Groups, & Global Seeder...")
    out_file = build_preparatory_template()
    print(f"[OK] Full template ready: {out_file}")


if __name__ == "__main__":
    main()
