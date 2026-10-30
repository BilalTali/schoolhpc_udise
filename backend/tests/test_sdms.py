"""SDMS students for the current session: the background fetch, the encrypted copy, the page view and the Excel.
A made-up SDMS and made-up students - nothing here reaches UDISE+."""
import io
import time

import pytest
from openpyxl import load_workbook

from backend.services import hpc_sessions, sdms_data, udise_sessions
from backend.udise import client, sdms

STUDENTS = [{"studentId": 11, "studentCodeNat": "PEN11", "studentName": "TEST CHILD A", "classId": 2, "classDesc": "Class 2",
             "sectionDesc": "A", "gender": 2, "dob": "2018-01-01", "fatherName": "TEST FATHER", "formStatus": 6,
             "socialCategoryList": [{"id": 1}], "uuidStatusDesc": "Verified"},
            {"studentId": 12, "studentCodeNat": "PEN12", "studentName": "TEST CHILD B", "classId": 1, "classDesc": "Class 1",
             "sectionDesc": "A", "gender": 1, "dob": "2019-01-01", "formStatus": 0, "cwsnYN": 1,
             "impairmentType": [5]}]                                            # SDMS keeps some answers as lists


class FakeSdms:
    ended = False

    def __init__(self, saved):
        pass

    def school_id(self):
        return 9000001

    def school(self, sid):
        return {"schoolId": sid, "schoolName": "TEST SCHOOL", "yearId": 13, "sessionStartDate": "01/04/2026",
                "sessionEndDate": "31/03/2027"}

    def classes(self, sid):
        return [{"classId": 1, "classDesc": "Class 1", "totalBoys": 1, "totalGirls": 0, "totalEnrollment": 1},
                {"classId": 2, "classDesc": "Class 2", "totalBoys": 0, "totalGirls": 1, "totalEnrollment": 1}]

    def students(self, sid):
        if FakeSdms.ended:
            raise sdms.SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card, then fetch again.")
        return STUDENTS

    def mother_tongues(self, state_id):
        return [{"id": 83, "code": 83, "description": "KASHMIRI - Kashmiri"}]

    def media(self, school_id):
        return [{"id": 19, "code": "19", "description": "English"}]

    def enrolment(self, student_id):
        return {"admnNumber": f"ADM{student_id}", "previousClassExamResult": {"1": "Pass"}}

    def facility(self, student_id):
        if student_id == 12:
            raise client.UdiseError("SDMS answered HTTP 500.")
        return {"textBooks": 1}


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sdms_data, "Sdms", FakeSdms)
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})
    sdms_data.JOBS.clear()
    FakeSdms.ended = False
    return tmp_path


def wait(school):
    for _ in range(100):
        job = sdms_data.progress(school)["job"]
        if job and job["status"] != "RUNNING":
            return job
        time.sleep(0.05)
    raise AssertionError("the fetch did not finish")


def test_every_student_is_fetched_kept_encrypted_and_shown_by_class(world):
    assert sdms_data.start("s1")["started"]
    job = wait("s1")
    assert job["status"] == "COMPLETED" and job["done"] == job["total"] == 2
    raw = (world / "school_s1" / "sdms_current.json").read_text(encoding="utf-8")
    assert "TEST CHILD" not in raw and "PEN11" not in raw                # personal details: encrypted
    view = sdms_data.view("s1")
    assert view["session"] == "2026-27" and [c["class"] for c in view["classes"]] == ["Class 1", "Class 2"]
    assert [s["name"] for s in view["students"]] == ["TEST CHILD B", "TEST CHILD A"]   # class 1 first
    b = view["students"][0]
    assert b["problems"] == ["facility: SDMS answered HTTP 500."] and b["admission_no"] == "ADM12"
    assert b["form"] == "Not started" and view["students"][1]["form"] == "Completed"     # SDMS: 6 done, 0 not started
    assert sdms_data.progress("s1")["saved"]["problems"] == 1


def test_the_excel_follows_the_form_one_sheet_per_class_and_the_totals(world):
    sdms_data.start("s2")
    wait("s2")
    wb = load_workbook(io.BytesIO(sdms_data.excel("s2")))
    assert wb.sheetnames == ["Classes", "All students", "Class 1", "Class 2"]
    ws = wb["All students"]
    tabs = [c.value for c in ws[1] if c.value]
    assert tabs == ["Student", "1. General Information", "2. Enrolment Details", "3. Other Details"]
    head = [c.value for c in ws[2]]
    assert "Student's Name (as per School record/School Admission Register)" in head
    assert "Admission Number in Present School" in head and "Whether CWSN?" in head
    row = dict(zip(head, [c.value for c in ws[3]]))                       # class 1 first: TEST CHILD B
    assert row["Gender (as per School record/School Admission Register)"] == "Male"     # words, not codes
    assert row["Admission Number in Present School"] == "ADM12" and row["Form status"] == "Not Started"
    assert row["If Yes, Type of impairment (code)"] == "5" and row["Whether CWSN?"] == "Yes"
    assert wb["Class 2"].max_row == 3 and ws.max_row == 4


def test_each_student_comes_with_the_whole_form_in_words(world):
    sdms_data.start("s5")
    wait("s5")
    a = sdms_data.view("s5")["students"][1]                               # TEST CHILD A
    tabs = {sec["section"]: {f["label"]: f["value"] for f in sec["fields"]} for sec in a["details"]}
    assert tabs["1. General Information"]["Gender (as per School record/School Admission Register)"] == "Female"
    assert tabs["2. Enrolment Details"]["Admission Number in Present School"] == "ADM11"
    assert tabs["Student"]["Form status"] == "Completed"


def test_an_ended_session_stops_the_fetch_with_what_to_do(world):
    FakeSdms.ended = True
    sdms_data.start("s3")
    job = wait("s3")
    assert job["status"] == "FAILED" and "Connect again" in job["error"]
    assert sdms_data.view("s3") is None


def test_no_fetch_without_an_sdms_connection(world, monkeypatch):
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {})
    result = sdms_data.start("s4")
    assert result["started"] is False and "Connect UDISE+" in result["error"]


def test_the_completion_sheet_lists_only_the_required_fields_and_what_is_missing(world):
    sdms_data.start("s6")
    wait("s6")
    wb = load_workbook(io.BytesIO(sdms_data.completion_excel("s6")))
    assert wb.sheetnames == ["To complete"]
    ws = wb["To complete"]
    head = [c.value for c in ws[2]]
    assert head[:5] == ["Class", "Section", "Student's Name", "Father's Name (parentage)", "PEN"]
    assert "Medium of Instruction" in head and "Height (cm)" in head and "Remark" not in head
    rows = {r[2]: dict(zip(head, r)) for r in ws.iter_rows(min_row=3, values_only=True)}
    b = rows["TEST CHILD B"]                                              # a made-up child with nearly nothing filled
    assert b["To complete"].startswith(tuple(str(n) for n in range(1, 50))) and "Mother's Name (empty)" in b["To complete"]
    assert b["Type of impairment (if CWSN)"] == "5"                     # CWSN: needed, and given
    a = rows["TEST CHILD A"]
    assert a["Type of impairment (if CWSN)"] == "not needed"             # not CWSN
    summary = sdms_data.completion_summary("s6")
    assert summary["students"] == 2 and summary["to_complete"] == 2 and summary["fields"]


def test_the_new_admissions_sheet_has_the_add_student_fields_then_the_rest_with_drop_downs(world):
    sdms_data.start("s7")
    wait("s7")
    wb = load_workbook(io.BytesIO(sdms_data.admission_template("s7")))
    ws = wb["New students"]
    head = [c.value for c in ws[3]]
    assert head[:3] == ["Class *", "Section *", "Student's Name (as per School Admission Register) *"]
    assert "Guardian's Name" in head and "AADHAAR Number of Student (12 digits) *" in head and "Mother Tongue *" in head
    assert wb["Lists"].sheet_state == "hidden" and [c.value for c in wb["Lists"]["A"][1:3]] == ["Class 1", "Class 2"]
    assert len(ws.data_validations.dataValidation) > 10 and not ws.protection.sheet
    assert ws.max_row <= 3 or all(c.value is None for c in ws[4])     # no existing student's details in it
