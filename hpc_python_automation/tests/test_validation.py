"""
Tests for Excel import, parsing, multi-sheet support, and data validation rules.
"""
from pathlib import Path
from excel.importer import import_preparatory_workbook
from excel.validator import validate_workbook_records, validate_student_record, ValidationReport

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "data" / "hpc_preparatory_template.xlsx"


def test_template_two_sheets_and_validates():
    """Verify that the generated template has two sheets, imports the exemplary sample, and passes validation with 0 errors."""
    assert TEMPLATE_PATH.exists()

    # Sheet 1: Blank template (no records)
    blank_records = import_preparatory_workbook(TEMPLATE_PATH, sheet_name="HPC_Preparatory_Blank")
    assert len(blank_records) == 0

    # Sheet 2: Sample filled student
    sample_records = import_preparatory_workbook(TEMPLATE_PATH, sheet_name="Sample_Filled_Student")
    assert len(sample_records) == 1

    first = sample_records[0]["data"]
    assert first["student_name"] == "Aarav Sharma"
    assert first["admission_number"] == "558"
    assert first["grade"] == "Grade 5"

    # Validate the complete sample record
    report = validate_workbook_records(sample_records)
    assert report.is_valid is True
    assert len(report.errors) == 0


def test_auto_detect_data_sheet():
    """Verify that auto-detecting the data sheet finds the populated sample sheet when Sheet 1 is blank."""
    records = import_preparatory_workbook(TEMPLATE_PATH)
    assert len(records) == 1
    assert records[0]["data"]["student_name"] == "Aarav Sharma"


def test_validation_mandatory_fields():
    """Verify that missing mandatory fields trigger errors."""
    invalid_record = {
        "_row_number": 4,
        "data": {
            "admission_number": "",
            "student_name": "",
            "dob": "",
            "gender": "UnknownGender",
            "grade": "Grade 99",
        }
    }
    report = ValidationReport()
    validate_student_record(invalid_record, report)
    assert report.is_valid is False
    assert len(report.errors) >= 4


def test_attendance_bounds_check():
    """Verify that days present exceeding working days triggers an error."""
    record = {
        "_row_number": 5,
        "data": {
            "admission_number": "1001",
            "student_name": "Rohan Verma",
            "dob": "10/05/2014",
            "gender": "Boy",
            "grade": "Grade 4",
            "working_days": "180",
            "days_present": "200",  # Invalid: 200 > 180
            "comp_VAC1_1": "proficient",
        }
    }
    report = ValidationReport()
    validate_student_record(record, report)
    assert report.is_valid is False
    assert any("Days present" in e.message for e in report.errors)


def test_competency_rating_validation():
    """Verify that invalid competency ratings are caught."""
    record = {
        "_row_number": 6,
        "data": {
            "admission_number": "1002",
            "student_name": "Priya Singh",
            "dob": "12/03/2015",
            "gender": "Girl",
            "grade": "Grade 3",
            "working_days": "200",
            "days_present": "190",
            "comp_VAC1_1": "super_excellent",  # Invalid
        }
    }
    report = ValidationReport()
    validate_student_record(record, report)
    assert report.is_valid is False
    assert any("Invalid rating" in e.message for e in report.errors)
