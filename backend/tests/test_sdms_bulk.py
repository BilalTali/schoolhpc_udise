"""Bulk tools from Excel: class / section shift, Send to Dropbox, Import from the Dropbox and AADHAAR corrections -
download the sheet, check a filled one (nothing sent), run one row first, never a row twice. A made-up SDMS."""
import copy
import io
import time

import pytest
from openpyxl import load_workbook

from backend.services import hpc_sessions, sdms_aadhaar, sdms_bulk, sdms_data, udise_sessions

BASE = {"schoolId": 77, "gender": 2, "dob": "01/01/2019", "fatherName": "TEST FATHER", "isUuidAvailable": 1,
        "uuid": "********1234", "formStatus": 6, "uuidStatus": 1}
STUDENTS = [
    {**BASE, "studentId": 1, "studentName": "TEST UKG", "studentCodeNat": "PEN1", "classId": -1, "classDesc": "UKG/KG2/PP1",
     "sectionId": 11, "sectionDesc": "A"},
    {**BASE, "studentId": 2, "studentName": "TEST FIVE", "studentCodeNat": "PEN2", "classId": 5, "classDesc": "V",
     "sectionId": 51, "sectionDesc": "A"},
    {**BASE, "studentId": 3, "studentName": "TEST LEFT", "studentCodeNat": "PEN3", "classId": 5, "classDesc": "V",
     "sectionId": 52, "sectionDesc": "B", "uuidStatus": 2, "uuidValidateRemarks": "AADHAAR/Name/Gender/DOB Mismatched"},
]
SECTIONS = [{"classId": -1, "sectionData": [{"sectionId": 11, "sectionDesc": "A"}]},
            {"classId": 1, "sectionData": [{"sectionId": 12, "sectionDesc": "A"}, {"sectionId": 13, "sectionDesc": "B"}]},
            {"classId": 5, "sectionData": [{"sectionId": 51, "sectionDesc": "A"}, {"sectionId": 52, "sectionDesc": "B"}]}]


class FakeSdms:
    posts = []

    def __init__(self, saved):
        pass

    def school_id(self):
        return 77

    def school(self, sid):
        return {"schoolId": 77, "yearId": 13, "stateId": 101}

    def classes(self, sid):
        return [{"classId": -1, "classDesc": "UKG/KG2/PP1"}, {"classId": 5, "classDesc": "V"}]

    def students(self, sid):
        return copy.deepcopy(STUDENTS)

    def mother_tongues(self, state):
        return []

    def media(self, school):
        return []

    def enrolment(self, sid):
        return {}

    def facility(self, sid):
        return {}

    def get(self, path):
        if path.startswith("api/v2/school/class/sections/"):
            return copy.deepcopy(SECTIONS)
        if path.startswith("api/school/progression-status/"):
            return {"1": "Promoted/Passed by Examination", "2": "Promoted/Passed without Examination"}
        raise AssertionError(path)

    def post_answer(self, path, body):
        FakeSdms.posts.append((path, copy.deepcopy(body)))
        if path.startswith("api/students/import/search/"):
            if body["studentCodeNat"] == "DROP1" and body["dob"] == "05/05/2016":
                return {"status": True, "data": [{"studentId": 900, "studentName": "TEST DROPBOX", "classToPromoted": 5}]}
            return {"status": False, "error": {"message": "Student not found in Dropbox"}}
        if path == "api/v2/students/send-dropbox" and body["studentId"] == 3 and body["attendance"] == 7:
            return {"status": False, "error": {"message": "Attendance is not valid"}}
        return {"status": True, "message": "Done", "tnxReqNo": "T1"}


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sdms_data, "Sdms", FakeSdms)
    monkeypatch.setattr(sdms_bulk, "Sdms", FakeSdms)
    monkeypatch.setattr(sdms_bulk.time, "sleep", lambda s: None)
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})
    FakeSdms.posts = []
    sdms_data.JOBS.clear()
    sdms_bulk.JOBS.clear()
    sdms_data.start("s1")
    for _ in range(100):
        if sdms_data.progress("s1")["job"]["status"] != "RUNNING":
            break
        time.sleep(0.05)


def _fill(kind, values):
    """The downloaded sheet, with {pen or row number: {column: value}} filled in."""
    wb = load_workbook(io.BytesIO(sdms_bulk.template("s1", kind)))
    ws = wb[sdms_bulk.SPECS[kind]["title"][:31]]
    head = [c.value for c in ws[2]]
    for key, cells in values.items():
        row = key if isinstance(key, int) else next(r for r in range(3, ws.max_row + 1) if ws.cell(row=r, column=1).value == key)
        for col, v in cells.items():
            ws.cell(row=row, column=head.index(col) + 1, value=v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _run(kind, rows=None):
    assert sdms_bulk.start("s1", kind, rows)["started"]
    for _ in range(400):
        job = sdms_bulk.state("s1", kind)["job"]
        if job["status"] != "RUNNING":
            return job
        time.sleep(0.05)
    raise AssertionError("still running")


def test_shift_allows_a_class_change_only_from_kg_to_class_one_and_any_section(world):
    sheet = _fill("shift", {"PEN1": {"New class": "I", "New section": "B"}, "PEN2": {"New class": "VI", "New section": "A"},
                            "PEN3": {"New section": "a"}})
    plan = sdms_bulk.validate("s1", "shift", sheet, "shift.xlsx")
    rows = {r["pen"]: r for r in plan["rows"]}
    assert rows["PEN1"]["problems"] == [] and rows["PEN3"]["problems"] == []
    assert "only between Nursery/KG" in rows["PEN2"]["problems"][0]
    assert plan["ready"] == 2 and FakeSdms.posts == []                        # checking sends nothing
    job = _run("shift")
    assert job["status"] == "COMPLETED", job["error"]
    assert all(not r["error"] for r in job["results"])
    assert [b for _, b in FakeSdms.posts] == [{"studentId": 1, "classId": 1, "sectionId": 13, "classChangeGroup": 1},
                                              {"studentId": 3, "classId": 5, "sectionId": 51, "classChangeGroup": 1}]
    assert sdms_bulk.start("s1", "shift")["started"] is False                 # never twice
    again = sdms_bulk.validate("s1", "shift", sheet, "shift.xlsx")            # the same sheet again: shown as done
    assert again["ready"] == 0 and again["done"] == 2


def test_dropbox_checks_type_reason_and_dates_and_keeps_sdms_refusal(world):
    left = {"Type": "Left school with TC", "Session": "Mid session (studying here this year)", "Last class studied": "V",
            "Last attended date (DD/MM/YYYY)": "10/10/2026", "TC issue date (DD/MM/YYYY)": "12/10/2026",
            "Attendance (days)": 120, "Reason": "Family Relocation / Transfer"}
    sheet = _fill("dropbox", {"PEN2": left, "PEN3": {**left, "Attendance (days)": 7},
                              "PEN1": {**left, "Type": "Left school without TC (Dropout)", "Last attended date (DD/MM/YYYY)": "01/01/2099"}})
    plan = sdms_bulk.validate("s1", "dropbox", sheet, "d.xlsx")
    rows = {r["pen"]: r for r in plan["rows"]}
    assert any("Last attended date" in p for p in rows["PEN1"]["problems"])
    assert any("Student Absent for Many Days" in p for p in rows["PEN1"]["problems"])
    one = next(r["row"] for r in plan["rows"] if r["pen"] == "PEN2")
    job = _run("dropbox", [one])                                               # one first
    assert len(job["results"]) == 1 and not job["results"][0]["error"]
    assert FakeSdms.posts[0] == ("api/v2/students/send-dropbox", {
        "academicYear": 13, "lastClassStudied": 5, "lastAttendedDate": "10/10/2026", "tcIssueDate": "12/10/2026",
        "attendance": 120, "studentstatus2": 221, "dropoutType": 2, "studentPen": "PEN2", "studentId": 2})
    job = _run("dropbox")                                                      # then the rest: PEN3, refused
    assert [r["error"] for r in job["results"]] == ["SDMS did not accept it: Attendance is not valid"]
    assert sdms_bulk.state("s1", "dropbox")["plan"]["ready"] == 1              # refused rows can be sent again


def test_import_looks_up_each_pen_on_the_dropbox_then_submits(world):
    row = {"PEN": "DROP1", "Date of birth (DD/MM/YYYY)": "05/05/2016", "Class to admit": "V", "Section": "B",
           "Admission date (DD/MM/YYYY)": "01/10/2026", "Progression status": "Promoted/Passed by Examination",
           "Marks (%)": 75, "Attendance (days)": 200}
    sheet = _fill("import", {3: row, 4: {**row, "PEN": "NOPE"}})
    plan = sdms_bulk.validate("s1", "import", sheet, "i.xlsx")
    good, bad = plan["rows"]
    assert good["problems"] == [] and good["name"] == "TEST DROPBOX"
    assert bad["problems"] == ["SDMS: Student not found in Dropbox"]
    assert all(p.startswith("api/students/import/search/77") for p, _ in FakeSdms.posts)
    _run("import")
    assert FakeSdms.posts[-1] == ("api/students/import/submit/", {
        "studentId": 900, "schoolId": 77, "classId": 5, "progressionStatusCy": "1", "marksCy": "75", "attendanceCy": 200,
        "sectionId": 52, "admissionDate": "01/10/2026"})


def test_aadhaar_sheet_lists_only_students_to_fix_and_needs_consent(world, monkeypatch):
    wb = load_workbook(io.BytesIO(sdms_bulk.template("s1", "aadhaar")))
    ws = wb["AADHAAR corrections"]
    assert [ws.cell(row=r, column=1).value for r in range(3, ws.max_row + 1)] == ["PEN3"]
    sent = []
    monkeypatch.setattr(sdms_aadhaar, "correct", lambda *a: sent.append(a) or {"ok": True, "verified": True})
    card = {"AADHAAR number (12 digits, from the card)": "2345 6789 0123", "Name exactly as on the AADHAAR": "TEST LEFT",
            "Gender (as on the card)": "Female", "Date of birth (DD/MM/YYYY, as on the card)": "01/01/2019",
            "Parent's consent given (Yes/No)": "No"}
    plan = sdms_bulk.validate("s1", "aadhaar", _fill("aadhaar", {"PEN3": card}), "a.xlsx")
    assert "consent" in plan["rows"][0]["problems"][0]
    sdms_bulk.validate("s1", "aadhaar", _fill("aadhaar", {"PEN3": {**card, "Parent's consent given (Yes/No)": "Yes"}}), "a.xlsx")
    job = _run("aadhaar")
    assert job["results"][0]["message"] == "Saved and verified with UIDAI"
    assert sent == [("s1", 3, "234567890123", "TEST LEFT", None, None)]       # gender and date unchanged: not sent


def test_the_routes_are_not_named_like_the_modules():
    from backend.routers import schools
    assert schools.sdms_bulk is sdms_bulk
