"""School Register, phase 2: settings (working days, max marks), the School Data workbook down and back up - checked
first, saved only on apply, identity never changed from Excel, repeated uploads change nothing. MOCKED PARAKH session
(only its academic year is used); the register is filled by the phase-1 fetch with a made-up PARAKH."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.database import SessionLocal
from backend.main import app
from backend.models.register import RegisterImport, RegisterSetting, RegisterStudentData
from backend.services import register_data, school_register
from backend.tests.conftest import session_headers
from backend.tests.test_school_register import FakeSchoolParakh, _fetch, _school
from backend.tests.conftest import make_lookups

API = "/api/v1"


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(school_register, "Lookups", lambda client, stage: make_lookups("PREPARATORY"))
    monkeypatch.setattr(register_data, "session_of", lambda school_id: "2627")
    client = TestClient(app)
    h = _school(client, "44444444401", [("datateach1", "TLOGIN1")])
    other = _school(client, "44444444402", [])
    from backend.models.entities import Teacher
    with SessionLocal() as db:
        school_id = db.query(Teacher).filter_by(username="datateach1").one().school_id
        for model in (RegisterStudentData, RegisterImport, RegisterSetting):
            db.query(model).filter_by(school_id=school_id).delete()
        db.commit()
    from backend.models.register import RegisterStudent
    with SessionLocal() as db:
        db.query(RegisterStudent).filter_by(school_id=school_id).delete()
        db.commit()
    _fetch(school_id, FakeSchoolParakh())
    return client, h, other, school_id


def _settings(client, h):
    days = [20, 22, 0, 24, 25, 24, 24, 23, 18, 0, 20, 22]
    r = client.put(f"{API}/school/register/settings", headers=h, json={"stage": "Preparatory", "values": {
        "working_days": days, "max_marks": {str(n): 100 for n in range(1, 7)}}})
    assert r.status_code == 200, r.text
    return days


def _book(client, h):
    r = client.get(f"{API}/school/register/data.xlsx", headers=h)
    assert r.status_code == 200, r.text
    return load_workbook(io.BytesIO(r.content))


def _bytes(wb):
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _upload(client, h, wb, name="School_Data.xlsx"):
    content = wb if isinstance(wb, bytes) else _bytes(wb)
    return client.post(f"{API}/school/register/data/check", headers=h,
                       files={"file": (name, content, "application/octet-stream")})


def test_settings_are_versioned_and_teachers_read_them_only(world):
    client, h, *_ = world
    days = _settings(client, h)
    got = client.get(f"{API}/school/register/settings", headers=h, params={"stage": "Preparatory"}).json()
    assert got["values"]["working_days"] == days and got["version"] == 1
    bad = client.put(f"{API}/school/register/settings", headers=h, json={"stage": "Preparatory",
                                                                          "values": {"working_days": [40] + [None] * 11}})
    assert bad.status_code == 422 and "April" in bad.text
    th, _ = session_headers("datateach1")
    assert client.get(f"{API}/teacher/register/settings", headers=th, params={"stage": "Preparatory"}).json()["version"] == 1
    assert client.put(f"{API}/school/register/settings", headers=th,
                      json={"stage": "Preparatory", "values": {}}).status_code in (401, 403)


def test_2_3_4_5_the_workbook_round_trip_saves_linked_to_the_parakh_ids(world):
    client, h, _, school_id = world
    _settings(client, h)
    wb = _book(client, h)
    ws = wb["Preparatory"]
    heads = [c.value for c in ws[2]]
    assert heads[:3] == ["Register ID", "PARAKH ID", "Student name (PARAKH)"] and heads[11] == "Apr present (20)"
    assert "Mother's name" not in heads and heads[8:11] == ["Father's name", "Name on the HPC card",
                                                             "Mother's or guardian's name (if chosen)"]
    assert ws.max_row == 102                                                         # every student, exact names
    assert {ws.cell(row=r, column=3).value for r in range(3, 103)} >= {"STUDENT 1-00", "STUDENT 4-09"}
    for r in range(3, 103):                                                          # test 3: the school fills in
        ws.cell(row=r, column=9, value="ABDUL RASHID")
        ws.cell(row=r, column=10, value="Father" if r % 2 else None)               # empty: the father (PARAKH's default)
        ws.cell(row=r, column=12, value=18)                                          # April present
        ws.cell(row=r, column=28, value=75)                                          # R1 marks
    filled = _bytes(wb)
    check = _upload(client, h, filled).json()
    assert check["summary"]["ready"] == 100 and check["summary"]["problem"] == 0, check["summary"]
    assert client.get(f"{API}/school/register", headers=h).json()["students"][0]["entered"] is None   # not saved yet
    done = client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True}).json()
    assert done["saved"] == 100 and done["status"] == "APPLIED"
    row = next(s for s in client.get(f"{API}/school/register", headers=h).json()["students"] if s["student_id"] == "500001")
    assert row["entered"]["present"] == 18 and row["entered"]["percent"] == 90.0 and row["entered"]["marks"] == 1
    cards = register_data.for_cards(school_id, "Preparatory", "2627", "500001")    # what phase 3 hands the card
    assert cards["a1_working_1"] == 20 and cards["a1_present_1"] == 18 and cards["d_1_obtained"] == 75
    assert cards["a1_guardian_relation"] == "Father" and cards["a1_guardian_name"] == "ABDUL RASHID"
    assert "a1_present_3" not in cards                                               # no data: never 0
    again = _upload(client, h, filled).json()                                        # test 15: same file again
    assert again["summary"]["ready"] == 0 and again["summary"]["unchanged"] == 100 and again["summary"]["already_applied_at"]


def test_identity_edits_bad_numbers_duplicates_and_left_out_rows_are_reported(world):
    client, h, *_ = world
    _settings(client, h)
    wb = _book(client, h)
    ws = wb["Preparatory"]
    ws.cell(row=3, column=3, value="SOMEONE ELSE")                                   # name edited in Excel
    ws.cell(row=4, column=12, value=25)                                              # 25 present of 20
    ws.cell(row=5, column=28, value=120)                                             # 120 of 100
    ws.cell(row=6, column=10, value="Guardian")                                      # Guardian without a name
    ws.cell(row=7, column=14, value=3)                                               # June: 0 working days
    ws.delete_rows(100, 3)                                                           # three students left out
    for c in range(1, 12):                                                           # row 99 a copy of row 8
        ws.cell(row=99, column=c, value=ws.cell(row=8, column=c).value)
    check = _upload(client, h, wb).json()
    by_row = {r["row"]: r for r in check["rows"]}
    assert by_row[3]["outcome"] == "review" and "student name was changed" in by_row[3]["problems"][0]
    assert "25 days present, but 20 working days" in by_row[4]["problems"][0]
    assert "120 marks, but the max is 100" in by_row[5]["problems"][0]
    assert "write the guardian's name" in by_row[6]["problems"][0]
    assert "3 days present, but 0 working days" in by_row[7]["problems"][0]
    assert "also on row 8" in by_row[99]["problems"][0]
    assert check["summary"]["left_out"] == {"Preparatory": 4}
    students = client.get(f"{API}/school/register", headers=h).json()["students"]
    assert all(s["entered"] is None for s in students)                              # a check saves nothing


def test_a_workbook_of_another_school_or_template_is_refused(world):
    client, h, other, _ = world
    _settings(client, h)
    wb = _book(client, h)
    r = _upload(client, other, wb)
    assert r.status_code == 422 and "another school" in r.text
    wb["_meta"]["B1"] = "old-template"
    assert "older or other template" in _upload(client, h, wb).text
    th, _ = session_headers("datateach1")
    assert client.get(f"{API}/school/register/data.xlsx", headers=th).status_code in (401, 403)


def test_apply_needs_confirmation_and_the_latest_check(world):
    client, h, *_ = world
    _settings(client, h)
    wb = _book(client, h)
    first = _upload(client, h, wb).json()
    second = _upload(client, h, wb).json()
    assert client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": second["id"]}).status_code == 400
    stale = client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": first["id"], "confirm": True})
    assert stale.status_code == 422 and "not the latest" in stale.text


def test_fetch_parents_from_udise_reaches_students_admitted_since_the_full_fetch(world, monkeypatch, tmp_path):
    """MOCKED UDISE+: a quick read of SDMS's student list; a new admission gets its parents by name + date of birth."""
    client, h, _, school_id = world
    from backend.services import hpc_sessions, udise_sessions
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    monkeypatch.setattr("backend.services.sdms_data.load", lambda sid: None)       # no full SDMS fetch yet
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"connected": True}}})

    class FakeSdms:
        def __init__(self, saved):
            pass

        def school_id(self):
            return 1

        def students(self, sid):
            return [{"studentId": 7, "studentName": "STUDENT 1-00", "dob": "01/05/2016", "fatherName": "NEW FATHER",
                     "motherName": "NEW MOTHER"}]
    monkeypatch.setattr("backend.udise.sdms.Sdms", FakeSdms)
    assert client.get(f"{API}/school/register/data", headers=h).json()["parents_source"]["kind"] is None
    r = client.post(f"{API}/school/register/parents/fetch", headers=h)
    assert r.status_code == 200 and r.json()["students"] == 1, r.text
    assert client.get(f"{API}/school/register/data", headers=h).json()["parents_source"]["kind"] == "quick"
    ws = _book(client, h)["Preparatory"]
    row = next(r for r in range(3, ws.max_row + 1) if ws.cell(row=r, column=3).value == "STUDENT 1-00")
    assert ws.cell(row=row, column=9).value == "NEW FATHER"                         # (no mother's name column)


def test_fetch_parents_says_when_udise_is_not_connected(world, monkeypatch):
    client, h, *_ = world
    from backend.services import udise_sessions
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {}})
    r = client.post(f"{API}/school/register/parents/fetch", headers=h)
    assert r.status_code == 422 and "not connected" in r.text


def test_mother_as_the_name_on_the_card_uses_the_one_name_column(world):
    client, h, _, school_id = world
    _settings(client, h)
    wb = _book(client, h)
    ws = wb["Preparatory"]
    ws.cell(row=3, column=10, value="Mother")
    ws.cell(row=3, column=11, value="SHAHEENA BEGUM")
    sid = ws.cell(row=3, column=2).value
    check = _upload(client, h, wb).json()
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True})
    cards = register_data.for_cards(school_id, "Preparatory", "2627", sid)
    assert cards["a1_guardian_relation"] == "Mother" and cards["a1_guardian_name"] == "SHAHEENA BEGUM"
    again = _book(client, h)["Preparatory"]                                           # shown again in the next download
    assert again.cell(row=3, column=10).value == "Mother" and again.cell(row=3, column=11).value == "SHAHEENA BEGUM"


def test_phase3_a_save_to_parakh_carries_the_schools_values_over_the_teachers(world):
    """Every save path (card editor, workbook upload, class check) goes through sync.build_payloads: the School
    Register's values win there, so a teacher cannot change attendance, the parent on the card or marks."""
    import json as _json
    import backend.services.register_data  # noqa: F401  (registers the hook, as the app does at start)
    from backend.hpc import sync
    from backend.tests.conftest import blank_student, filled_row
    client, h, _, school_id = world
    _settings(client, h)
    wb = _book(client, h)
    ws = wb["Preparatory"]
    ws.cell(row=3, column=9, value="ABDUL RASHID")
    ws.cell(row=3, column=12, value=18)                                              # April present
    ws.cell(row=3, column=28, value=75)                                              # R1 marks
    sid = ws.cell(row=3, column=2).value
    check = _upload(client, h, wb).json()
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True})

    data = blank_student("PREPARATORY")
    data.student_id = sid
    data.record.setdefault("sch_info", {})["school_udise"] = "44444444401"
    data.record.setdefault("stu_info", {})["school_cur_ay_code"] = "2627"
    row = filled_row("PREPARATORY")
    row.update({"a1_present_1": 5, "a1_guardian_name": "TEACHER TYPED", "d_1_obtained": 10})   # the teacher's values
    payloads, _ = sync.build_payloads("PREPARATORY", data, row, make_lookups("PREPARATORY"))
    a1 = _json.loads(next(p for p in payloads if p["hpc_col"] == "part_a1")["formdata"])
    assert a1["attn"]["1"][0] == 20 and a1["attn"]["2"][0] == 18                    # school's working days, present
    assert a1["gen"][24] == "Abdul Rashid" and a1["gen"][23] == "FATHER"           # capitals tidied (A11)
    d = next(p for p in payloads if p["hpc_col"] == "hpc_credit")["formdata"]
    d = _json.loads(d) if isinstance(d, str) else d
    assert [str(v) for v in d["credit"][0]] == ["100", "75"]                         # school's max and marks
    other = blank_student("PREPARATORY")                                              # another school: untouched
    payloads, _ = sync.build_payloads("PREPARATORY", other, row, make_lookups("PREPARATORY"))
    assert _json.loads(next(p for p in payloads if p["hpc_col"] == "part_a1")["formdata"])["attn"]["2"][0] == 5
