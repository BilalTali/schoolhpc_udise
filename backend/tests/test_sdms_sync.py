"""SDMS updates from the filled completion sheet: validate (nothing sent) then sync (only changed tabs, AADHAAR never
changed, read back to confirm). A made-up SDMS and made-up students - nothing here reaches UDISE+."""
import copy
import io
import time

import pytest
from openpyxl import load_workbook

from backend.services import hpc_sessions, sdms_data, sdms_sync, udise_sessions
from backend.udise import client, sdms

GENERAL = {"studentId": 12, "studentCodeNat": "PEN12", "studentName": "TEST CHILD B", "classId": 6, "classDesc": "VI",
           "sectionId": 1, "sectionDesc": "A", "schoolId": 77, "gender": 1, "dob": "01/01/2014", "fatherName": "TEST FATHER",
           "motherName": "", "uuid": "********1234", "nameAsUuid": "TEST CHILD B", "address": "TEST VILLAGE ROAD",
           "pincode": 191111, "primaryMobile": "9000000001", "motherTongue": 83, "socCatId": 1, "minorityId": 1,
           "isBplYN": 1, "aayBplYN": 2, "ewsYN": 2, "cwsnYN": 2, "natIndYN": 1, "ooscYN": 2, "ooscMainstreamedYN": 9,
           "formStatus": 0}
ENROL = {"studentId": 12, "schoolId": 77, "admnNumber": None, "admnStartDate": "01/04/2020", "moiId": 0, "enrStatusPY": 1,
         "classPY": 5, "examResultPy": 1, "examMarksPy": 70.0, "attendancePy": 200, "mandatorySubjectGroup": None,
         "languageGroup": 1251}
FACILITY = {"studentId": 12, "schoolId": 77, "facilityYn": 1, "facProvided": [1, 2], "olympdsNlc": 2, "nccYn": 2, "nssYn": 2,
            "scoutsYn": 2, "heightInCm": 5, "weightInKg": 30, "distanceFrmSchool": 1, "parentEducation": 1}


class FakeSdms:
    """Holds one student's form; saves change it, like SDMS."""
    store = {}
    posts = []

    def __init__(self, saved):
        pass

    def school_id(self):
        return 77

    def school(self, sid):
        return {"schoolId": 77, "yearId": 13, "stateId": 101,
                "isFacilityAvailable": [{"id": 1, "fieldName": "Free Text Book"}, {"id": 2, "fieldName": "Free Uniforms"}]}

    def classes(self, sid):
        return [{"classId": 6, "classDesc": "VI", "totalEnrollment": 1}]

    def students(self, sid):
        return [copy.deepcopy(self.store["general"])]

    def mother_tongues(self, state):
        return [{"id": 83, "description": "KASHMIRI - Kashmiri"}, {"id": 1, "description": "Assamese - Assamese"}]

    def media(self, school):
        return [{"id": 19, "description": "English"}]

    def student(self, sid):
        return copy.deepcopy(self.store["general"])

    def enrolment(self, sid):
        return copy.deepcopy(self.store["enrolment"])

    def facility(self, sid):
        return copy.deepcopy(self.store["facility"])

    def post(self, path, body):
        FakeSdms.posts.append((path, copy.deepcopy(body)))
        tab = "general" if path.startswith("api/cy/students") else "enrolment" if "enrolment" in path else "facility"
        keys = {"enrolment": {"mandatorySubject": "mandatorySubjectGroup"}}.get(tab, {})
        for k, v in body.items():
            if tab == "general" and k in ("uuid", "nameAsUuid"):
                continue                                     # not updating the AADHAAR: SDMS keeps its own
            self.store[tab][keys.get(k, k)] = v
        return {"status": True, "message": "Saved", "data": {}}


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sdms_data, "Sdms", FakeSdms)
    monkeypatch.setattr(sdms_sync, "Sdms", FakeSdms)
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})
    FakeSdms.store = {"general": copy.deepcopy(GENERAL), "enrolment": copy.deepcopy(ENROL), "facility": copy.deepcopy(FACILITY)}
    FakeSdms.posts = []
    sdms_data.JOBS.clear()
    sdms_sync.JOBS.clear()
    sdms_data.start("s1")
    for _ in range(100):
        if sdms_data.progress("s1")["job"]["status"] != "RUNNING":
            break
        time.sleep(0.05)
    return tmp_path


def filled(edits):
    wb = load_workbook(io.BytesIO(sdms_data.completion_excel("s1")))
    ws = wb["To complete"]
    head = [c.value for c in ws[2]]
    for label, value in edits.items():
        ws.cell(row=3, column=head.index(label) + 1, value=value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def wait(school):
    for _ in range(100):
        job = sdms_sync.progress(school)["job"]
        if job and job["status"] != "RUNNING":
            return job
        time.sleep(0.05)
    raise AssertionError("the sync did not finish")


def test_validate_lists_each_change_in_words_and_the_cells_sdms_would_refuse(world):
    content = filled({"Mother's Name": "TEST MOTHER", "Medium of Instruction": "English", "Height (cm)": 128,
                      "Mother Tongue": "Klingon", "AADHAAR Number of Student": "999999999999"})
    result = sdms_sync.validate("s1", content, "sheet.xlsx")
    assert result["ok"]
    [b] = result["students"]
    changes = {c["label"]: (c["before"], c["after"]) for c in b["changes"]}
    assert changes["Mother's Name"] == ("", "TEST MOTHER") and changes["Medium of Instruction"] == ("", "English")
    assert changes["Height (cm)"] == ("5", "128")
    assert "AADHAAR Number of Student" not in changes                    # never changed from here
    assert b["problems"] == ["Mother Tongue: a choice from SDMS's list (use the drop-down)"]
    assert any("Admission Number" in m for m in b["still_missing"])       # still empty after this sheet
    assert result["ready"] == 0 and FakeSdms.posts == []                  # a row with a problem is not sent; nothing sent


def test_sync_saves_only_the_changed_tabs_never_the_aadhaar_and_reads_back(world):
    sdms_sync.validate("s1", filled({"Mother's Name": "TEST MOTHER", "Medium of Instruction": "English",
                                     "Admission Number in Present School": "A-12"}), "sheet.xlsx")
    assert sdms_sync.start("s1")["started"]
    job = wait("s1")
    assert job["status"] == "COMPLETED" and job["results"][0]["error"] is None
    assert job["results"][0]["saved"] == ["General Information", "Enrolment Details"]   # Other Details unchanged: not sent
    paths = [p for p, _ in FakeSdms.posts]
    assert paths == ["api/cy/students/12", "api/v2/students/enrolment/12"]
    general = FakeSdms.posts[0][1]
    assert general["uuidUpdateYN"] == 2 and general["uuid"] == "" and general["nameAsUuid"] == ""
    assert general["motherName"] == "TEST MOTHER" and general["fatherName"] == "TEST FATHER"   # the rest as SDMS holds it
    enrol = FakeSdms.posts[1][1]
    assert enrol["moiId"] == 19 and enrol["admnNumber"] == "A-12" and enrol["classPY"] == 5
    assert FakeSdms.store["general"]["uuid"] == "********1234"           # the AADHAAR stayed
    view = sdms_data.view("s1")
    assert view["students"][0]["mother"] == "TEST MOTHER"                 # the kept copy shows the saved form


def test_a_refused_save_is_reported_and_the_next_student_goes_on(world, monkeypatch):
    def refuse(self, path, body):
        raise client.UdiseError("SDMS did not accept it: Mother name invalid")
    monkeypatch.setattr(FakeSdms, "post", refuse)
    sdms_sync.validate("s1", filled({"Mother's Name": "TEST MOTHER"}), "sheet.xlsx")
    sdms_sync.start("s1")
    job = wait("s1")
    assert job["status"] == "COMPLETED" and job["results"][0]["error"] == "SDMS did not accept it: Mother name invalid"


def test_the_sync_route_needs_the_persons_confirmation(world):
    from backend.routers import schools
    from fastapi import HTTPException

    class Admin:
        id = "s1"
    with pytest.raises(HTTPException) as e:
        schools.sdms_sync_start(schools.SdmsSyncRequest(confirm=False), admin=Admin())
    assert e.value.status_code == 400 and FakeSdms.posts == []


def test_an_ended_session_stops_the_sync(world, monkeypatch):
    def ended(self, sid):
        raise sdms.SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card.")
    sdms_sync.validate("s1", filled({"Mother's Name": "TEST MOTHER"}), "sheet.xlsx")
    monkeypatch.setattr(FakeSdms, "student", ended)
    sdms_sync.start("s1")
    job = wait("s1")
    assert job["status"] == "FAILED" and "Connect again" in job["error"] and FakeSdms.posts == []


def full(edits, sheet="All students"):
    wb = load_workbook(io.BytesIO(sdms_data.excel("s1")))
    ws = wb[sheet]
    head = [c.value for c in ws[2]]
    for label, value in edits.items():
        ws.cell(row=3, column=head.index(label) + 1, value=value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_the_all_details_workbook_untouched_changes_nothing(world):
    result = sdms_sync.validate("s1", full({}), "all.xlsx")
    assert result["ok"] and result["ready"] == 0
    assert all(not s["changes"] and not s["problems"] for s in result["students"])


def test_the_all_details_workbook_is_a_bulk_update(world):
    content = full({"Mother's Name": "TEST MOTHER", "Medium of Instruction": "English", "Student's Height (in CMs)": 128,
                    "Whether BPL beneficiary?": "No", "Class/Section Roll Number": "7",
                    "Approximate Distance of student's residence to school": "2 - Between 1-3 Kms",
                    "Central Scholarship": "Yes", "Class": "X"})
    result = sdms_sync.validate("s1", content, "all.xlsx")
    [b] = result["students"]
    changes = {c["label"]: (c["before"], c["after"]) for c in b["changes"]}
    assert changes == {"Mother's Name": ("", "TEST MOTHER"), "Medium of Instruction": ("", "English"),
                       "Student's Height (in CMs)": ("5", "128"), "Whether BPL beneficiary?": ("Yes", "No"),
                       "Class/Section Roll Number": ("", "7"),
                       "Approximate Distance of student's residence to school": ("1 - Less than 1 km", "2 - Between 1-3 Kms")}
    assert b["problems"] == [] and set(b["ignored"]) == {"Central Scholarship", "Class"}
    assert result["ready"] == 1 and FakeSdms.posts == []
    sdms_sync.start("s1")
    job = wait("s1")
    assert job["status"] == "COMPLETED" and job["results"][0]["error"] is None, job
    assert [p for p, _ in FakeSdms.posts] == ["api/cy/students/12", "api/v2/students/enrolment/12", "api/v2/AY/students/facility/12"]
    assert FakeSdms.posts[0][1]["isBplYN"] == 2 and FakeSdms.posts[1][1]["rollNumber"] == "7"
    assert FakeSdms.posts[2][1]["heightInCm"] == 128 and FakeSdms.posts[2][1]["distanceFrmSchool"] == 2


def test_a_class_sheet_edit_counts_and_a_clash_is_flagged(world):
    wb = load_workbook(io.BytesIO(full({"Mother's Name": "TEST MOTHER"}, sheet="VI")))
    assert sdms_sync.validate("s1", full({"Mother's Name": "TEST MOTHER"}, sheet="VI"), "all.xlsx")["ready"] == 1
    ws = wb["All students"]
    head = [c.value for c in ws[2]]
    ws.cell(row=3, column=head.index("Mother's Name") + 1, value="OTHER MOTHER")
    out = io.BytesIO()
    wb.save(out)
    [b] = sdms_sync.validate("s1", out.getvalue(), "all.xlsx")["students"]
    assert any("changed differently" in p for p in b["problems"])


def test_the_sheet_has_only_incomplete_forms(world, monkeypatch):
    ws = load_workbook(io.BytesIO(sdms_data.completion_excel("s1")))["To complete"]
    assert ws.max_row == 3 and ws.cell(row=3, column=5).value == "PEN12"          # the incomplete student
    real = sdms_data.sdms_form.completion
    monkeypatch.setattr(sdms_data.sdms_form, "completion",
                        lambda s, m: [{**c, "issue": ""} for c in real(s, m)])     # every form complete
    ws = load_workbook(io.BytesIO(sdms_data.completion_excel("s1")))["To complete"]
    assert ws.max_row == 3 and "complete - nothing to fill" in ws.cell(row=3, column=1).value


def test_a_saved_student_is_not_ready_again_and_never_sent_twice(world):
    sdms_sync.validate("s1", filled({"Mother's Name": "TEST MOTHER"}), "sheet.xlsx")
    assert sdms_sync.last_plan("s1")["ready"] == 1
    sdms_sync.start("s1")
    assert wait("s1")["status"] == "COMPLETED"
    plan = sdms_sync.last_plan("s1")
    assert plan["ready"] == 0 and plan["already_saved"] == 1 and plan["students"][0]["done"] is True
    posts = len(FakeSdms.posts)
    again = sdms_sync.start("s1")
    assert again["started"] is False and "already on SDMS" in again["error"] and len(FakeSdms.posts) == posts


def test_disconnecting_udise_stops_a_running_save(world, monkeypatch):
    sdms_sync.validate("s1", filled({"Mother's Name": "TEST MOTHER"}), "sheet.xlsx")
    calls = {"n": 0}

    def session(sid):
        calls["n"] += 1                                   # connected when the save starts, then disconnected
        return {"services": {"sdms": {"connected": calls["n"] == 1}}}
    monkeypatch.setattr(udise_sessions, "_load", session)
    sdms_sync.start("s1")
    job = wait("s1")
    assert job["status"] == "FAILED" and "disconnected" in job["error"] and FakeSdms.posts == []
