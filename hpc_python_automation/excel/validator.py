"""
Validator: validates imported student rows against business rules, portal requirements,
and strict DOM character length limits.
"""
from typing import List, Dict, Any, Tuple
import re
from datetime import datetime

VALID_RATINGS = {"beginner", "proficient", "advance"}
VALID_OVERALL_RATINGS = {"beginner", "proficient", "advance"}
VALID_GENDERS = {"boy", "girl", "other", "male", "female"}
VALID_GRADES = {"grade 3", "grade 4", "grade 5", "3", "4", "5",
                "grade 6", "grade 7", "grade 8", "6", "7", "8"}
VALID_YES_NO = {"yes", "no", "true", "false", "1", "0", ""}

MAX_LENGTHS = {
    "hand_finger_1": 13,
    "hand_finger_2": 15,
    "hand_finger_3": 13,
    "hand_finger_4": 24,
    "hand_finger_5": 23,
    "grow_up_goal": 54,
    "admired_person": 24,
    "my_calling_name": 23,
    "my_age": 2,
    "fav_food": 83,
    "fav_games": 83,
    "fav_festival": 83,
    "three_things_1": 37,
    "three_things_2": 37,
    "three_things_3": 37,
    "peer_feedback": 35,
    "parent_feedback": 105,
    "activity_name": 200,
    "teacher_remarks": 400,
    "credits_earned": 5,
}


class ValidationError:
    def __init__(self, row: int, field: str, message: str, severity: str = "ERROR"):
        self.row = row
        self.field = field
        self.message = message
        self.severity = severity

    def __str__(self):
        return f"Row {self.row} [{self.field}]: {self.message}"


class ValidationReport:
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, row: int, field: str, message: str):
        self.errors.append(ValidationError(row, field, message, severity="ERROR"))

    def add_warning(self, row: int, field: str, message: str):
        self.warnings.append(ValidationError(row, field, message, severity="WARNING"))

    def summary(self) -> str:
        status = "PASSED" if self.is_valid else "FAILED"
        return f"Validation {status}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)."


def validate_student_record(record: Dict[str, Any], report: ValidationReport) -> None:
    row = record.get("_row_number", 0)
    data = record.get("data", {})

    # 1. Admission Number
    adm = data.get("admission_number", "").strip()
    if not adm:
        report.add_error(row, "admission_number", "Admission Number is mandatory.")

    # 2. Student Name
    name = data.get("student_name", "").strip()
    if not name:
        report.add_error(row, "student_name", "Student Name is mandatory.")
    elif len(name) < 2:
        report.add_error(row, "student_name", "Student Name is too short.")

    # 3. Date of Birth (Optional - read-only on portal)
    dob = data.get("dob", "").strip()
    if dob:
        parsed_dob = False
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                datetime.strptime(dob, fmt)
                parsed_dob = True
                break
            except ValueError:
                pass
        if not parsed_dob:
            report.add_warning(row, "dob", f"DOB '{dob}' does not match expected DD/MM/YYYY or YYYY-MM-DD format.")

    # 4. Gender (Optional - read-only on portal)
    gender = data.get("gender", "").strip().lower()
    if gender and gender not in VALID_GENDERS:
        report.add_error(row, "gender", f"Invalid gender '{gender}'. Must be Male, Female, or Other.")

    # 5. Grade
    grade = data.get("grade", "").strip().lower()
    if not grade:
        report.add_error(row, "grade", "Grade is mandatory.")
    elif grade not in VALID_GRADES:
        report.add_error(row, "grade", f"Invalid grade '{grade}'. Must be Grade 3, Grade 4, or Grade 5.")

    # 6. Monthly & Total Attendance checks
    months = ("apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "jan", "feb", "mar")
    for m in months:
        w_val = data.get(f"{m}_working_days", "").strip()
        p_val = data.get(f"{m}_present_days", "").strip()
        if w_val.isdigit() and p_val.isdigit():
            if int(p_val) > int(w_val):
                report.add_error(row, f"{m}_present_days", f"{m.upper()} present days ({p_val}) exceeds working days ({w_val}).")

    working_days = data.get("working_days", "").strip()
    days_present = data.get("days_present", "").strip()
    if working_days.isdigit() and days_present.isdigit():
        w_int = int(working_days)
        p_int = int(days_present)
        if p_int > w_int:
            report.add_error(row, "days_present", f"Days present ({p_int}) cannot exceed working days ({w_int}).")

    # 7. Interests (Yes/No)
    for k, v in data.items():
        if k.startswith("interest_"):
            if v and v.strip().lower() not in VALID_YES_NO:
                report.add_warning(row, k, f"Interest field '{k}' has unexpected value '{v}'. Expected Yes or No.")

    # 8. Character Length Limits (Strict Portal Compliance)
    for field, max_len in MAX_LENGTHS.items():
        val = str(data.get(field, "")).strip()
        if len(val) > max_len:
            report.add_error(
                row,
                field,
                f"Field '{field}' exceeds portal maximum character limit of {max_len} (currently {len(val)} characters)."
            )

    # 9. Competencies (Part B)
    comp_count = 0
    for k, v in data.items():
        if k.startswith("comp_"):
            comp_count += 1
            val_clean = v.strip().lower()
            if val_clean and val_clean not in VALID_RATINGS:
                report.add_error(row, k, f"Invalid rating '{v}'. Allowed: beginner, proficient, advance.")

    if comp_count == 0:
        report.add_warning(row, "competencies", "No Part-B competency columns were found in this record.")


def validate_workbook_records(records: List[Dict[str, Any]]) -> ValidationReport:
    report = ValidationReport()
    if not records:
        report.add_error(0, "file", "Workbook contains no student records.")
        return report

    for rec in records:
        validate_student_record(rec, report)

    return report
