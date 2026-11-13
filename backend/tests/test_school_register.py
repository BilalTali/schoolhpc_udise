"""School Register, phase 1 (docs/school_register_plan.md): the school fetches every student from PARAKH; teachers
get only the students of the classes PARAKH maps to them; schools never see each other's students.
PARAKH is a made-up client here (MOCKED provider) - nothing reaches the real portal."""
import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.hpc.portal import PortalError
from backend.main import app
from backend.models.entities import Teacher
from backend.models.register import RegisterStudent
from backend.services import school_register
from backend.tests.conftest import make_lookups, session_headers

API = "/api/v1"
GRADE = 8                                        # Grade 5 in the made-up lists
SPLIT = {1: 35, 2: 30, 3: 25, 4: 10}             # section -> students; section 4 has no teacher


class FakeSchoolParakh:
    """The school login's view: 100 Preparatory students, three teachers with one section each."""

    def __init__(self, students=None, refuse_school_list=False):
        self.rows = students if students is not None else self.make_students()
        self.refuse = refuse_school_list
        self.calls = []

    @staticmethod
    def make_students():
        rows, sid = [], 500000
        for sec, n in SPLIT.items():
            for i in range(n):
                sid += 1
                rows.append({"id": sid, "full_name": f"STUDENT {sec}-{i:02d}", "grade_id": GRADE, "section_id": sec,
                             "std_reg_id": f"REG{sid}", "std_apaar_id": f"{sid:012d}", "hpc_status": "PENDING"})
        return rows

    def school_roster(self, stage):
        self.calls.append(("school_roster", stage))
        if self.refuse:
            raise PortalError("not allowed")
        return list(self.rows) if stage == "Preparatory" else []

    def roster(self, stage):
        self.calls.append(("roster", stage))
        return list(self.rows) if stage == "Preparatory" else []

    def student(self, stage, sid, hpc_col=None):
        self.calls.append(("student", sid))
        return {"hpc_id": str(sid), "sch_info": {"school_udise": "01010101010"},
                "stu_info": {"dob": "2016-05-01", "gender": "FEMALE", "school_admission_number": f"A{sid}"}}

    def school_teachers(self):
        # as PARAKH sends them (live, 2026-11-01): staff_fname/lname, ct 1 = class teacher, ct 0 = subject teacher only
        return [{"id": 9000 + sec, "staff_fname": "PARAKH", "staff_lname": f"Teacher {sec}", "teacher_code": f"TLOGIN{sec}",
                 "grade_section_mapping": [{"grd": GRADE, "sec": sec, "ct": 1}, {"grd": GRADE, "sec": 4, "ct": 0}]}
                for sec in (1, 2, 3)]

    def teacher_grade_sections(self, tid):
        return []


def _school(client, udise, teachers):
    body = {"udise_code": udise, "school_name": f"Register School {udise[-1]}", "state": "JK", "district": "Budgam",
            "admin_name": "Admin", "admin_email": f"{udise}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=body).status_code in (201, 409)
    headers, _ = session_headers(udise)
    for username, login in teachers:
        client.post(f"{API}/school/teachers", headers=headers, json={
            "teacher_name": username, "username": username, "password": "secret123", "assigned_stages": ["Preparatory"]})
        with SessionLocal() as db:
            t = db.query(Teacher).filter_by(username=username).one()
            t.hpc_login_id = login
            db.commit()
    return headers


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(school_register, "Lookups", lambda client, stage: make_lookups("PREPARATORY"))
    client = TestClient(app)
    a = _school(client, "22222222201", [("regteach1", "TLOGIN1"), ("regteach2", "TLOGIN2"), ("regteach3", "TLOGIN3")])
    b = _school(client, "22222222202", [("regteachb", "TLOGIN9")])
    with SessionLocal() as db:
        school_a = db.query(Teacher).filter_by(username="regteach1").one().school_id
        school_b = db.query(Teacher).filter_by(username="regteachb").one().school_id
        db.query(RegisterStudent).filter(RegisterStudent.school_id.in_([school_a, school_b])).delete()
        db.commit()
    return client, a, b, school_a, school_b


def _fetch(school_id, fake):
    school_register.JOBS.pop(school_id, None)
    school_register.JOBS[school_id] = {"status": "RUNNING", "done": 0, "total": 0, "stages": {}, "notes": []}
    school_register._run(school_id, fake, ["Foundational", "Preparatory", "Middle"])
    return school_register.JOBS[school_id]


def test_1_11_15_the_school_fetches_all_100_students_once_and_sees_the_unassigned(world):
    client, a, _, school_a, _ = world
    job = _fetch(school_a, FakeSchoolParakh())
    assert job["status"] == "COMPLETED", job
    assert job["stages"]["Preparatory"] == {"added": 100, "updated": 0, "missing": 0, "listed": 100}
    reg = client.get(f"{API}/school/register", headers=a).json()
    assert reg["summary"]["Preparatory"] == {"students": 100, "assigned": 90, "unassigned": 10, "missing_on_parakh": 0}
    first = next(s for s in reg["students"] if s["student_id"] == "500001")
    assert first["student_name"] == "STUDENT 1-00" and first["apaar_id"] == "000000500001"      # exactly as PARAKH
    assert first["dob"] == "2016-05-01" and first["teachers"] == ["regteach1"]
    again = _fetch(school_a, FakeSchoolParakh())                                          # test 15: no duplicates
    assert again["stages"]["Preparatory"]["added"] == 0 and again["stages"]["Preparatory"]["updated"] == 100
    with SessionLocal() as db:
        assert db.query(RegisterStudent).filter_by(school_id=school_a).count() == 100


def test_6_8_19_teachers_get_only_their_classes_from_the_register(world):
    client, *_ = world
    _fetch(world[3], FakeSchoolParakh())
    counts = {}
    for n in (1, 2, 3):
        h, _ = session_headers(f"regteach{n}")
        rows = client.get(f"{API}/teacher/register/students", headers=h).json()["students"]
        counts[n] = len(rows)
        assert {r["section_id"] for r in rows} == {n}
    assert counts == {1: 35, 2: 30, 3: 25}
    h1, _ = session_headers("regteach1")
    assert client.get(f"{API}/school/register", headers=h1).status_code in (401, 403)           # teachers: no register
    assert client.post(f"{API}/school/register/fetch", headers=h1, json={}).status_code in (401, 403)


def test_18_a_school_never_sees_another_schools_students(world):
    client, a, b, school_a, _ = world
    _fetch(school_a, FakeSchoolParakh())
    assert client.get(f"{API}/school/register", headers=b).json()["students"] == []
    hb, _ = session_headers("regteachb")
    assert client.get(f"{API}/teacher/register/students", headers=hb).json()["students"] == []


def test_a_student_parakh_stops_listing_is_marked_not_deleted(world):
    client, a, _, school_a, _ = world
    _fetch(school_a, FakeSchoolParakh())
    fewer = FakeSchoolParakh.make_students()[1:]
    job = _fetch(school_a, FakeSchoolParakh(fewer))
    assert job["stages"]["Preparatory"]["missing"] == 1
    reg = client.get(f"{API}/school/register", headers=a).json()
    assert reg["summary"]["Preparatory"]["students"] == 100 and reg["summary"]["Preparatory"]["missing_on_parakh"] == 1
    h1, _ = session_headers("regteach1")
    assert len(client.get(f"{API}/teacher/register/students", headers=h1).json()["students"]) == 34


def test_parakh_refusing_the_school_list_falls_back_and_says_so(world):
    _, _, _, school_a, _ = world
    fake = FakeSchoolParakh(refuse_school_list=True)
    job = _fetch(school_a, fake)
    assert job["status"] == "COMPLETED" and job["stages"]["Preparatory"]["listed"] == 100
    assert any("refused the school list" in n for n in job["notes"]) and ("roster", "Preparatory") in fake.calls


def test_the_school_dashboard_counts_come_from_the_register(world):
    client, a, _, school_id, _ = world
    _fetch(school_id, FakeSchoolParakh())
    stats = client.get(f"{API}/school/stats", headers=a).json()
    assert stats["from_register"] is True and stats["total_students"] == 100            # not the teachers' rosters
    assert stats["total_teachers"] == 3 and stats["teacher_accounts"] == 3              # PARAKH's teachers, logins


def test_10_the_school_sees_where_every_card_stands(world, monkeypatch, tmp_path):
    """Phase 4: from what actually happened - upload results, card saves, drafts, PARAKH's own status."""
    client, a, _, school_id, _ = world
    rows = FakeSchoolParakh.make_students()
    rows[5]["hpc_status"] = "COMPLETED"                                            # PARAKH itself: complete
    _fetch(school_id, FakeSchoolParakh(rows))
    from backend.models.entities import StudentRecord, UploadJob
    from backend.services import audit, hpc_sessions
    with SessionLocal() as db:
        t1 = db.query(Teacher).filter_by(username="regteach1").one()
        job = UploadJob(teacher_id=t1.id, original_filename="class.xlsx", detected_stage="Preparatory", status="PARTIAL_SUCCESS")
        db.add(job)
        db.flush()
        for sid, state, err in (("500001", "SUCCESS", None), ("500002", "FAILED", "PARAKH refused: timeout"),
                                ("500003", "PENDING", None), ("500004", "INVALID", "Mother Tongue: required")):
            db.add(StudentRecord(job_id=job.id, admission_number=sid, student_name=sid, status=state, error_message=err))
        db.commit()
        t1_id = t1.id
    audit.record(f"teacher:{t1_id}", "save_to_parakh", "student", "500007", None, {"status": "COMPLETED", "via": "card"})
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path / i)
    (tmp_path / t1_id / "drafts" / "2627").mkdir(parents=True)
    (tmp_path / t1_id / "drafts" / "2627" / "preparatory_500008.json").write_text("{}")
    reg = client.get(f"{API}/school/register", headers=a).json()
    card = {s["student_id"]: s["card"] for s in reg["students"]}
    assert card["500001"]["status"] == "Verified on PARAKH" and card["500001"]["teacher"] == "regteach1"
    assert card["500002"]["status"] == "Submission failed" and "timeout" in card["500002"]["detail"]
    assert card["500003"]["status"] == "Submitted"
    assert card["500004"]["status"] == "Requires correction"
    assert card["500006"]["status"] == "Verified on PARAKH" and "PARAKH lists" in card["500006"]["detail"]
    assert card["500007"]["status"] == "Verified on PARAKH"                         # saved from the card editor
    assert card["500008"]["status"] == "Teacher work in progress"
    assert card["500009"]["status"] == "Assigned to teacher"
    assert card["500091"]["status"] == "Fetched"                                    # section 4: no teacher
    assert reg["card_status"]["Preparatory"]["Fetched"] == 10


def test_13_udise_apaar_parakh_comparison_runs_on_the_register(world, monkeypatch):
    """Phase 5 (MOCKED UDISE+): the whole school from the register, not the teachers' classes."""
    _, _, _, school_id, _ = world
    _fetch(school_id, FakeSchoolParakh())
    from backend.services import udise_parakh

    def u(name, apaar="", gender="Female", cls=5):
        return {"name": name, "parent": "", "father": "", "section": "A", "adm_no": "", "class": f"{cls} A",
                "class_id": cls, "dob": "01/05/2016", "gender": gender, "apaar": apaar, "pen": "", "status": "Form complete"}
    udise = [u("STUDENT 1-00", apaar="000000500001"),                       # matched by APAAR, same
             u("STUDENT 1-01", apaar="", gender="Male"),                     # matched by name + DOB: gender differs
             u("NOT ON PARAKH")]
    monkeypatch.setattr(udise_parakh, "udise_students", lambda sid: udise)
    r = udise_parakh.compare(school_id, [])
    assert r["source"] == "School Register" and r["counts"]["parakh"] == 100 and r["counts"]["matched"] == 2
    assert r["counts"]["only_udise"] == 1 and r["counts"]["only_parakh"] == 98
    by_name = {m["udise"]["name"]: m for m in r["matched"]}
    assert by_name["STUDENT 1-00"]["by"] == "APAAR ID" and by_name["STUDENT 1-00"]["differs"] == []
    assert "gender" in by_name["STUDENT 1-01"]["differs"]
    assert r["apaar"]["only_parakh"] == 1                                       # PARAKH has it, UDISE+ does not
    assert by_name["STUDENT 1-00"]["parakh"]["status"].startswith("Card: ")


def test_14_reports_school_comparison_and_teacher(world, monkeypatch):
    """Phase 6: reports from the saved records; teachers get only their own students and no school report."""
    import io
    from openpyxl import load_workbook
    from backend.services import udise_parakh
    client, a, _, school_id, _ = world
    _fetch(school_id, FakeSchoolParakh())
    r = client.get(f"{API}/school/register/reports/school.xlsx", headers=a)
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Students", "By teacher", "Needs attention"]
    assert wb["Students"].max_row == 101 and wb["By teacher"].max_row == 4          # 100 students, 3 teachers
    summary = {row[0].value: row for row in wb["Summary"].iter_rows(min_row=2)}
    assert summary["Preparatory"][1].value == 100 and summary["Preparatory"][3].value == 10   # 10 without a teacher

    udise = [{"name": "STUDENT 1-00", "parent": "", "father": "", "section": "A", "adm_no": "", "class": "5 A", "class_id": 5,
              "dob": "01/05/2016", "gender": "Female", "apaar": "", "pen": "", "status": "Form complete"}]
    monkeypatch.setattr(udise_parakh, "udise_students", lambda sid: udise)          # MOCKED UDISE+
    dash = client.get(f"{API}/school/register/reports/reconciliation", headers=a).json()
    assert dash["ok"] and dash["counts"]["matched"] == 1 and dash["apaar"]["only_parakh"] == 1
    rec = load_workbook(io.BytesIO(client.get(f"{API}/school/register/reports/reconciliation.xlsx", headers=a).content))
    assert rec.sheetnames == ["Summary", "APAAR", "Differences", "Only on UDISE+", "Only on PARAKH"]
    assert rec["APAAR"]["F2"].value == "Only on PARAKH" and rec["Only on PARAKH"].max_row == 100

    h1, _ = session_headers("regteach1")
    mine = load_workbook(io.BytesIO(client.get(f"{API}/teacher/register/report.xlsx", headers=h1).content))
    assert mine["My students"].max_row == 36                                         # only their 35
    assert client.get(f"{API}/school/register/reports/school.xlsx", headers=h1).status_code in (401, 403)
    assert client.get(f"{API}/school/register/reports/reconciliation", headers=h1).status_code in (401, 403)
