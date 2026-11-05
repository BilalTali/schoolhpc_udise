"""AADHAAR verification and APAAR IDs: the groups (what each student needs), verifying again, correcting the details
to match the card, and generating an APAAR ID with the parent's consent. A made-up SDMS - nothing reaches UDISE+."""
import base64
import copy
import time

import pytest

from backend.services import hpc_sessions, sdms_aadhaar, sdms_data, udise_sessions
from backend.udise import sdms

KEY = base64.b64encode(b"0123456789abcdef").decode()
BASE = {"schoolId": 77, "classId": 1, "classDesc": "I", "sectionId": 1, "sectionDesc": "A", "gender": 2, "dob": "01/01/2019",
        "fatherName": "TEST FATHER", "motherName": "TEST MOTHER", "isUuidAvailable": 1, "uuid": "********1234",
        "formStatus": 6}
STUDENTS = [
    {**BASE, "studentId": 1, "studentName": "TEST OK", "studentCodeNat": "PEN1", "nameAsUuid": "TEST OK", "uuidStatus": 1,
     "uuidStatusDesc": "Verified From UIDAI against Name, Gender & DOB", "uuidValidateRemarks": "Correct"},
    {**BASE, "studentId": 2, "studentName": "TEST RETRY", "studentCodeNat": "PEN2", "nameAsUuid": "TEST RETRY", "uuidStatus": 0,
     "uuidStatusDesc": "AADHAAR not verified", "uuidValidateRemarks": "Technical/Auth Server Error Please Try After Some Time"},
    {**BASE, "studentId": 3, "studentName": "TEST MISMATCH", "studentCodeNat": "PEN3", "nameAsUuid": "TEST MISMACH", "uuidStatus": 2,
     "uuidStatusDesc": "Verification Failed From UIDAI", "uuidValidateRemarks": "AADHAAR/Name/Gender/DOB Mismatched"},
]


class FakeSdms:
    posts, gets = [], []
    verified = {2}                                          # UIDAI now says yes for student 2

    def __init__(self, saved):
        pass

    def school_id(self):
        return 77

    def school(self, sid):
        return {"schoolId": 77, "yearId": 13, "stateId": 101}

    def classes(self, sid):
        return [{"classId": 1, "classDesc": "I", "totalEnrollment": 3}]

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

    def key(self):
        return KEY

    def student(self, sid):
        return copy.deepcopy(next(s for s in STUDENTS if s["studentId"] == sid))

    def get_answer(self, path):
        FakeSdms.gets.append(path)
        sid = int(path.split("/")[-2])
        if sid in FakeSdms.verified:
            return {"status": True, "data": {"uuidStatus": 1, "uuidStatusDesc": "Verified From UIDAI against Name, Gender & DOB",
                                             "uuidValidateRemarks": "Correct", "uuidValidateDate": "30/10/2026"}}
        return {"status": False, "error": {"message": "Verification Failed From UIDAI",
                                           "data": {"uuidStatus": 2, "uuidStatusDesc": "Verification Failed From UIDAI",
                                                    "uuidValidateRemarks": "AADHAAR/Name/Gender/DOB Mismatched"}}}

    def post(self, path, body):
        FakeSdms.posts.append((path, copy.deepcopy(body)))
        FakeSdms.verified.add(body.get("studentId"))
        return {"status": True}

    def post_answer(self, path, body):
        FakeSdms.posts.append((path, copy.deepcopy(body)))
        if path.startswith("api/apaar/students/"):
            return {"status": True, "data": [{"studentId": 1, "apaarId": None, "apaarIdStatus": 0, "isApaarGenAllowed": 1,
                                               "apaarRemarksMessage": "Not generated", "mbuStatusDesc": "MBU Not Required"}]}
        return {"status": True, "message": "APAAR ID generated", "data": {"apaarId": "123456789012"}}


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sdms_data, "Sdms", FakeSdms)
    monkeypatch.setattr(sdms_aadhaar, "Sdms", FakeSdms)
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})
    FakeSdms.posts, FakeSdms.gets, FakeSdms.verified = [], [], {2}
    sdms_data.JOBS.clear()
    sdms_aadhaar.JOBS.clear()
    sdms_data.start("s1")
    for _ in range(100):
        if sdms_data.progress("s1")["job"]["status"] != "RUNNING":
            break
        time.sleep(0.05)


def test_each_student_is_grouped_by_what_it_needs_with_sdms_reason(world):
    view = sdms_aadhaar.overview("s1")
    assert view["counts"] == {"verified": 1, "retry": 1, "mismatch": 1, "no_aadhaar": 0, "apaar_ready": 1, "apaar_done": 0,
                              "apaar_waiting": 2}
    retry = next(r for r in view["students"] if r["student_id"] == 2)
    assert retry["group"] == "retry" and retry["reason"].startswith("Technical/Auth Server Error")


def test_verifying_again_asks_uidai_once_per_student_and_keeps_its_answer(world):
    assert sdms_aadhaar.start_verify("s1", [2, 3])["started"]
    for _ in range(100):
        job = sdms_aadhaar.progress("s1")["job"]
        if job["status"] != "RUNNING":
            break
        time.sleep(0.05)
    results = {r["student_id"]: r for r in job["results"]}
    assert results[2]["verified"] and not results[3]["verified"] and "Mismatched" in results[3]["reason"]
    assert FakeSdms.gets == ["api/v2/students/uuid-validate/2/1", "api/v2/students/uuid-validate/3/1"]
    assert sdms_aadhaar.overview("s1")["counts"]["verified"] == 2      # the kept copy shows UIDAI's new answer


def test_correcting_sends_the_card_details_encrypted_then_verifies(world):
    bad = sdms_aadhaar.correct("s1", 3, "12345", "TEST MISMATCH", None, None)
    assert bad["ok"] is False and "12 digits" in bad["error"] and FakeSdms.posts == []
    done = sdms_aadhaar.correct("s1", 3, "2345 6789 0123", "TEST MISMATCH", None, None)
    assert done["ok"] and done["verified"]
    path, body = FakeSdms.posts[0]
    assert path == "api/cy/students/3" and body["uuidUpdateYN"] == 1 and body["nameAsUuid"] == "TEST MISMATCH"
    assert body["uuid"] == sdms.encrypt("234567890123", KEY) and "234567890123" not in str(body)
    assert body["fatherName"] == "TEST FATHER"                          # the rest as SDMS holds it


def test_apaar_needs_a_verified_aadhaar_and_the_parents_consent(world):
    consent = {"relation": 1, "name": "TEST FATHER", "id_type": 1, "id_no": "XXXX1111", "place": "TEST PLACE", "date": "2026-10-28"}
    assert sdms_aadhaar.generate_apaar("s1", 2, consent)["ok"] is False          # AADHAAR not verified yet
    assert "Fill in" in sdms_aadhaar.generate_apaar("s1", 1, {**consent, "place": ""})["error"]
    done = sdms_aadhaar.generate_apaar("s1", 1, consent)
    assert done == {"ok": True, "apaar_id": "123456789012", "message": "APAAR ID generated"}
    path, body = FakeSdms.posts[-1]
    assert path == "api/apaar/generate" and body["studentId"] == 1 and body["uuidUpdateYN"] == 0
    assert body["uuid"] == sdms.encrypt("********1234", KEY) and body["date"] == "28/10/2026"
    assert body["consenterRelation"] == 1 and body["idType"] == 1
    view = sdms_aadhaar.overview("s1")
    assert view["counts"]["apaar_done"] == 1 and view["counts"]["apaar_ready"] == 0


def test_the_apaar_status_of_every_class_is_read_and_kept(world):
    assert sdms_aadhaar.read_apaar("s1") == {"ok": True, "students": 1}
    assert FakeSdms.posts[0] == ("api/apaar/students/77/1", {})        # SDMS's list: an empty body
    row = next(r for r in sdms_aadhaar.overview("s1")["students"] if r["student_id"] == 1)
    assert row["mbu"] == "MBU Not Required" and row["apaar_id"] is None


def test_no_route_hides_a_service_module_it_calls():
    """A route function named like a module it uses (sdms_aadhaar) replaces that module inside the router: every call
    to it then fails (a 500 on the page)."""
    import types
    from backend.routers import schools
    for name in ("sdms_aadhaar", "sdms_admit", "sdms_data", "sdms_sync", "udise_sessions", "audit", "hpc_sessions"):
        assert isinstance(getattr(schools, name), types.ModuleType), f"{name} is not the module any more"


def test_the_apaar_status_excel_has_completed_and_pending_with_what_to_do_next(world):
    import io
    from openpyxl import load_workbook
    from backend.services import sdms_apaar_excel
    sdms_aadhaar.read_apaar("s1")
    wb = load_workbook(io.BytesIO(sdms_apaar_excel.status_excel("s1")))
    assert wb.sheetnames == ["Completed (0)", "Pending (3)"]
    pending = {r[2]: r for r in wb["Pending (3)"].iter_rows(min_row=2, values_only=True)}
    assert "Generate the APAAR ID" in pending["TEST OK"][8]
    assert "Verify the AADHAAR again" in pending["TEST RETRY"][8] and pending["TEST RETRY"][6].startswith("Technical")
    assert "Correct the details" in pending["TEST MISMATCH"][8]


def test_apaar_from_the_consent_sheet_only_with_a_signed_consent_and_never_twice(world):
    import io
    from openpyxl import load_workbook
    from backend.services import sdms_apaar_excel
    sdms_aadhaar.read_apaar("s1")
    wb = load_workbook(io.BytesIO(sdms_apaar_excel.consent_template("s1")))
    ws = wb["APAAR consent"]
    assert [c.value for c in ws[3]][:4] == ["PEN1", "I", "A", "TEST OK"] and ws.max_row == 3      # only the ready student

    def upload(values):
        for col, v in enumerate(values, start=6):
            ws.cell(row=3, column=col, value=v)
        out = io.BytesIO()
        wb.save(out)
        return sdms_apaar_excel.validate("s1", out.getvalue(), "consent.xlsx")

    unsigned = upload(["Father", "TEST FATHER", "AADHAAR", "234567890123", "TEST PLACE", "28/10/2026", "No"])
    assert unsigned["rows"] == []                                        # no signed consent: left out
    bad = upload(["Father", "TEST FATHER", "PAN", "12345", "TEST PLACE", "28/10/2099", "Yes"])
    assert bad["ready"] == 0 and any("PAN" in p for p in bad["rows"][0]["problems"])
    assert any("not in the future" in p for p in bad["rows"][0]["problems"])
    good = upload(["Father", "TEST FATHER", "AADHAAR", "234567890123", "TEST PLACE", "28/10/2026", "Yes"])
    assert good["ready"] == 1 and "234567890123" not in str(good)        # consents are not shown back
    assert sdms_apaar_excel.start("s1")["started"]
    for _ in range(100):
        job = sdms_apaar_excel.state("s1")["job"]
        if job["status"] != "RUNNING":
            break
        time.sleep(0.05)
    assert job["results"][0]["apaar_id"] == "123456789012"
    path, body = FakeSdms.posts[-1]
    assert path == "api/apaar/generate" and body["idType"] == 1 and body["date"] == "28/10/2026"
    again = upload(["Father", "TEST FATHER", "AADHAAR", "234567890123", "TEST PLACE", "28/10/2026", "Yes"])
    assert again["ready"] == 0 and again["already"] == 1                 # never generated twice


def _fetch_again():
    sdms_data.start("s1")
    for _ in range(100):
        if sdms_data.progress("s1")["job"]["status"] != "RUNNING":
            break
        time.sleep(0.05)


def test_an_apaar_id_generated_on_the_udise_website_counts_as_generated(world, monkeypatch):
    # SDMS's student record carries the APAAR ID: no separate 'Read APAAR status' is needed to see it
    generated = [{**s, "apaarId": "999988887777", "apaarIdStatus": 1, "apaarIdStatusDesc": "Generated"} if s["studentId"] == 1
                 else {**s, "apaarId": None, "apaarIdStatus": 9, "apaarIdStatusDesc": ""} for s in STUDENTS]
    monkeypatch.setattr(FakeSdms, "students", lambda self, sid: copy.deepcopy(generated))
    _fetch_again()
    rows = {r["student_id"]: r for r in sdms_aadhaar.overview("s1")["students"]}
    assert rows[1]["apaar_id"] == "999988887777" and rows[1]["apaar_status"] == "Generated" and not rows[1]["apaar_ready"]
    assert rows[2]["apaar_id"] is None
    assert sdms_aadhaar.overview("s1")["counts"]["apaar_done"] == 1


def test_fetching_again_keeps_the_apaar_list_read_before(world):
    assert sdms_aadhaar.read_apaar("s1")["ok"]
    _fetch_again()
    kept = next(s for s in sdms_data.load("s1")["students"] if s["general"]["studentId"] == 1)
    assert kept["apaar"]["apaarRemarksMessage"] == "Not generated"


def test_the_next_step_says_pen_missing_only_when_the_pen_is_missing():
    from backend.services.sdms_apaar_excel import _next_step
    base = {"apaar_ready": False, "group": "verified", "reason": None, "pen": "23176636288", "apaar_status": None}
    assert "wait for the APAAR ID" in _next_step({**base, "apaar_allowed": 2,
                                                  "apaar_status": "Request for APAAR ID has been submitted successfully"})
    assert "PEN missing" in _next_step({**base, "pen": None})
    assert "generate again later" in _next_step({**base, "apaar_allowed": 1,
                                                 "apaar_status": "Error from APAAR services. Please regenerate APAAR Id"})
    assert "Generate the APAAR ID" in _next_step({**base, "apaar_ready": True})
