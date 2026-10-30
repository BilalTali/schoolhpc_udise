"""New admissions to SDMS from the filled sheet: validate (nothing sent), add once (AADHAAR encrypted as SDMS's page
does), fill the rest of the form, and SDMS's duplicate / age warnings left to the person. A made-up SDMS and made-up
students - nothing here reaches UDISE+."""
import base64
import copy
import io
import time

import pytest
from openpyxl import load_workbook

from backend.services import hpc_sessions, sdms_admit, sdms_data, udise_sessions
from backend.tests.test_sdms_sync import ENROL, FACILITY, GENERAL, FakeSdms as Existing
from backend.udise import sdms

KEY = base64.b64encode(b"0123456789abcdef").decode()


class FakeSdms(Existing):
    created = {}

    def classes(self, sid):
        return [{"classId": -1, "classDesc": "UKG/KG2/PP1", "totalEnrollment": 1}, {"classId": 1, "classDesc": "I", "totalEnrollment": 0},
                {"classId": 6, "classDesc": "VI", "totalEnrollment": 1}]

    def students(self, sid):
        kg = {**copy.deepcopy(GENERAL), "studentId": 30, "studentName": "TEST KG CHILD", "classId": -1, "classDesc": "UKG/KG2/PP1",
              "sectionId": 41, "sectionDesc": "A", "studentCodeNat": "PEN30"}
        return [copy.deepcopy(self.store["general"]), kg]

    def key(self):
        return KEY

    def post_answer(self, path, body):
        FakeSdms.posts.append((path, copy.deepcopy(body)))
        if body["studentName"] == "TEST TWIN":
            return {"status": False, "error": {"type": "error_duplicate_student", "message": "Student already exists"}}
        new_id = 900 + len(FakeSdms.created)
        FakeSdms.created[new_id] = body
        self.store = {"general": {**copy.deepcopy(GENERAL), "studentId": new_id, "studentName": body["studentName"],
                                  "classId": body["classId"], "sectionId": body["sectionId"]},
                      "enrolment": {"studentId": new_id, "schoolId": 77}, "facility": {"studentId": new_id, "schoolId": 77}}
        FakeSdms.store = self.store
        return {"status": True, "data": {"studentId": new_id, "studentName": body["studentName"]}}


ROW = {"Class": "UKG/KG2/PP1", "Section": "A", "Student's Name (as per School Admission Register)": "TEST NEW CHILD",
       "Gender": "Female", "Date of Birth (DD/MM/YYYY)": "05/06/2021", "Mother's Name": "TEST MOTHER",
       "Father's Name": "TEST FATHER", "AADHAAR Number of Student (12 digits)": "234567890123",
       "Name of Student as per AADHAAR": "TEST NEW CHILD", "Admission Date in Present School (DD/MM/YYYY)": "02/11/2025",
       "Mobile Number (10 digits)": "9000000002", "Whether CWSN?": "No", "Address (10 to 150 characters)": "TEST VILLAGE ROAD",
       "Pincode (6 digits)": "191111", "Mother Tongue": "KASHMIRI - Kashmiri", "Social Category": "General",
       "Minority Group": "Muslim", "Whether BPL beneficiary?": "Yes", "Whether AAY beneficiary?": "No",
       "Whether EWS / Disadvantaged Group?": "No", "Whether Indian National?": "Yes", "Out-of-School-Child?": "No",
       "Mainstreamed?": "Not applicable", "Admission Number in Present School": "N-1",
       "Status in Previous Academic Year": "Anganwadi/ ECCE Centre", "Medium of Instruction": "English",
       "Facilities provided?": "Yes", "Which facilities (comma separated)": "Free Text Book", "Olympiads / Competitions?": "No",
       "NCC": "No", "NSS": "No", "Scouts and Guides": "No", "Height (cm)": "95", "Weight (kg)": "14",
       "Distance to School": "1 - Less than 1 km", "Parents' Highest Education": "1 - Primary"}


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sdms_data, "Sdms", FakeSdms)
    monkeypatch.setattr(sdms_admit, "Sdms", FakeSdms)
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})
    FakeSdms.store = {"general": copy.deepcopy(GENERAL), "enrolment": copy.deepcopy(ENROL), "facility": copy.deepcopy(FACILITY)}
    FakeSdms.posts, FakeSdms.created = [], {}
    sdms_data.JOBS.clear()
    sdms_admit.JOBS.clear()
    sdms_data.start("s1")
    for _ in range(100):
        if sdms_data.progress("s1")["job"]["status"] != "RUNNING":
            break
        time.sleep(0.05)


def sheet(*rows):
    wb = load_workbook(io.BytesIO(sdms_data.admission_template("s1")))
    ws = wb["New students"]
    head = [str(c.value).replace(" *", "") for c in ws[3]]
    for r, values in enumerate(rows, start=4):
        for label, value in values.items():
            ws.cell(row=r, column=head.index(label) + 1, value=value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def wait():
    for _ in range(100):
        job = sdms_admit.progress("s1")["job"]
        if job and job["status"] != "RUNNING":
            return job
        time.sleep(0.05)
    raise AssertionError("adding did not finish")


def test_validate_finds_what_sdms_would_refuse_and_sends_nothing(world):
    bad = {**ROW, "Student's Name (as per School Admission Register)": "TEST 2", "AADHAAR Number of Student (12 digits)": "12345",
           "Mobile Number (10 digits)": "12345", "Section": "Z", "Mother Tongue": ""}
    result = sdms_admit.validate("s1", sheet(ROW, bad, {**ROW, "Class": "VI"}), "new.xlsx")
    assert result["ok"] and result["ready"] == 1 and result["with_problems"] == 2
    problems = result["rows"][1]["problems"]
    assert any(p.startswith("Student's Name") for p in problems) and any("12 digits" in p for p in problems)
    assert any(p.startswith("Mobile Number") for p in problems) and any("Section" in p for p in problems)
    assert "Mother Tongue: required" in problems
    assert any("Class II and above" in p for p in result["rows"][2]["problems"])
    assert "234567890123" not in str(result) and FakeSdms.posts == []          # no AADHAAR shown; nothing sent


def test_adding_creates_the_student_once_with_the_aadhaar_encrypted_then_fills_the_rest(world):
    sdms_admit.validate("s1", sheet(ROW), "new.xlsx")
    assert sdms_admit.start("s1")["started"]
    job = wait()
    [result] = job["results"]
    assert result["error"] is None and result["student_id"] == 900
    assert result["filled"] == ["General Information", "Enrolment Details", "Other Details"]
    path, body = FakeSdms.posts[0]
    assert path == "api/new-admission/AY" and body["classId"] == -1 and body["sectionId"] == 41
    assert body["uuid"] == sdms.encrypt("234567890123", KEY) and body["uuid"] != "234567890123"   # encrypted as SDMS does
    assert body["dob"] == "05/06/2021" and body["ageCheckSkipped"] == 2 and body["skipDuplicate"] == 2
    assert FakeSdms.store["enrolment"]["moiId"] == 19 and FakeSdms.store["facility"]["facProvided"] == [1]
    # the same sheet again: that row is never sent twice
    again = sdms_admit.validate("s1", sheet(ROW), "new.xlsx")
    assert again["already_added"] == 1 and again["ready"] == 0
    assert sdms_admit.start("s1")["started"] is False


def test_a_possible_duplicate_is_left_to_the_person(world):
    sdms_admit.validate("s1", sheet({**ROW, "Student's Name (as per School Admission Register)": "TEST TWIN",
                                     "Name of Student as per AADHAAR": "TEST TWIN"}), "new.xlsx")
    sdms_admit.start("s1")
    [result] = wait()["results"]
    assert result["student_id"] is None and "may be a student already on SDMS" in result["error"]
    assert len(FakeSdms.posts) == 1                                     # not tried again with the duplicate check off
