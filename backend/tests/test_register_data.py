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


def test_udise_parents_are_saved_into_the_register_by_themselves_only_where_empty(world, monkeypatch):
    """MOCKED UDISE+ (a full SDMS fetch): fetching the students fills every parent's name UDISE+ has, without a
    download or upload; a name the school entered stays."""
    client, h, _, school_id = world
    from backend.models.register import RegisterStudent
    with SessionLocal() as db:
        regs = db.query(RegisterStudent).filter_by(school_id=school_id).order_by(RegisterStudent.student_name).all()
        first, second = regs[0], regs[1]
        db.add(RegisterStudentData(school_id=school_id, student_id=second.id, session="2627", sources={},
                                   father_name="TYPED FATHER"))
        db.commit()
        people = [(r.student_name, r.apaar_id) for r in (first, second)]
    full = {"fetched_at": "2026-11-01T00:00:00Z", "students": [
        {"general": {"studentId": i, "studentName": n, "apaarId": d, "fatherName": f"UDISE FATHER {'AB'[i]}",
                     "motherName": "UDISE MOTHER"}} for i, (n, d) in enumerate(people)]}
    monkeypatch.setattr("backend.services.sdms_data.load", lambda sid: full)
    assert register_data.fill_from_udise(school_id) >= 1
    with SessionLocal() as db:
        a = db.query(RegisterStudentData).filter_by(student_id=first.id, session="2627").one()
        b = db.query(RegisterStudentData).filter_by(student_id=second.id, session="2627").one()
        assert (a.father_name, a.mother_name, a.sources["father_name"]) == ("UDISE FATHER A", "UDISE MOTHER", "udise")
        assert b.father_name == "TYPED FATHER" and b.mother_name == "UDISE MOTHER"
    assert register_data.for_cards(school_id, "Preparatory", "2627", first.parakh_student_id)["a1_guardian_name"] \
        == "UDISE FATHER A"
    assert register_data.fill_from_udise(school_id) == 0                         # a second run changes nothing


def test_parents_names_already_on_parakh_cards_come_in_with_the_fetch(world, monkeypatch):
    """MOCKED PARAKH: two students' A1 was saved on PARAKH (the card moved past A1); the fetch reads that page for
    them only and keeps the card's name in the register - over a UDISE+ name, never over one the school typed."""
    client, h, _, school_id = world
    import json
    from backend.models.register import RegisterStudent
    rows = FakeSchoolParakh.make_students()
    a, b = (str(rows[i]["id"]) for i in range(2))
    with SessionLocal() as db:
        reg = {r.parakh_student_id: r for r in db.query(RegisterStudent).filter_by(school_id=school_id)}
        db.add(RegisterStudentData(school_id=school_id, student_id=reg[a].id, session="2627",
                                   father_name="UDISE NAME", sources={"father_name": "udise"}))
        db.add(RegisterStudentData(school_id=school_id, student_id=reg[b].id, session="2627",
                                   father_name="TYPED NAME", sources={"father_name": "import:x"}))
        db.commit()

    class Started(FakeSchoolParakh):
        def student(self, stage, sid, hpc_col=None):
            sid = str(sid)
            if hpc_col == "part_a1":
                self.calls.append(("part_a1", sid))
                gen = [""] * 26
                gen[23], gen[24] = ("MOTHER", "SHAHEENA BEGUM") if sid == a else ("FATHER", "CARD FATHER")
                return {"formdata": json.dumps({"gen": gen})}
            out = super().student(stage, sid)
            if sid in (a, b):
                out["current_part"] = "A2"
            return out
    fake = Started()
    _fetch(school_id, fake)
    assert sorted(s for k, s in fake.calls if k == "part_a1") == sorted([a, b])     # only the started cards
    for pid, want in ((a, ("Mother", "SHAHEENA BEGUM")), (b, ("Father", "TYPED NAME"))):
        cards = register_data.for_cards(school_id, "Preparatory", "2627", pid)
        assert (cards["a1_guardian_relation"], cards["a1_guardian_name"]) == want, pid


def test_a_save_finds_the_register_when_parakh_lists_the_card_under_another_udise_code(world):
    """PARAKH's card carries a UDISE code other than the one the school registered with here (seen live: a
    re-coded school). The save still gets the register's parent and marks - found by the PARAKH student."""
    client, h, _, school_id = world
    from backend.models.register import RegisterStudent
    with SessionLocal() as db:
        reg = db.query(RegisterStudent).filter_by(school_id=school_id).first()
        db.add(RegisterStudentData(school_id=school_id, student_id=reg.id, session="2627", father_name="REGISTER FATHER",
                                   marks={"1": 30}, sources={}))
        db.commit()
        pid = reg.parakh_student_id
    record = {"sch_info": {"school_udise": "09999999999"}, "stu_info": {"school_cur_ay_code": "2627"}}
    got = register_data.card_values("Preparatory", record, pid)
    assert got["a1_guardian_name"] == "REGISTER FATHER" and got["d_1_obtained"] == 30
    assert register_data.card_values("Preparatory", record, "123456789") == {}       # not in any register


def test_a_save_never_takes_another_schools_register_values(world):
    """Two schools' registers hold the same PARAKH student (a transfer): the card's UDISE code - the school's own, or
    the one PARAKH files its cards under (kept at the fetch) - decides; never the other school's values."""
    client, h, other_h, school_id = world
    from backend.models.entities import School
    from backend.models.register import RegisterStudent
    with SessionLocal() as db:
        reg = db.query(RegisterStudent).filter_by(school_id=school_id).first()
        other = db.query(School).filter_by(udise_code="44444444402").one()
        db.query(RegisterStudent).filter_by(school_id=other.id).delete()
        twin = RegisterStudent(school_id=other.id, stage=reg.stage, parakh_student_id=reg.parakh_student_id,
                               student_name=reg.student_name)
        db.add(twin)
        db.flush()
        db.add(RegisterStudentData(school_id=school_id, student_id=reg.id, session="2627", father_name="MINE", sources={}))
        db.add(RegisterStudentData(school_id=other.id, student_id=twin.id, session="2627", father_name="THEIRS", sources={}))
        other.parakh_udise = "09999999999"                      # PARAKH files the other school's cards under this code
        db.commit()
        pid, mine_udise = reg.parakh_student_id, db.get(School, school_id).udise_code
    try:
        def name(udise):
            record = {"sch_info": {"school_udise": udise}, "stu_info": {"school_cur_ay_code": "2627"}}
            return register_data.card_values("Preparatory", record, pid).get("a1_guardian_name")
        assert name(mine_udise) == "MINE"
        assert name("09999999999") == "THEIRS"
        assert name("01234567890") is None                      # no school has that code and two registers hold him
        with register_data.acting_school(school_id):            # a teacher of my school saves: always my register,
            assert name("09999999999") == "MINE"                # whatever code PARAKH shows on the card
        with SessionLocal() as db:                              # two schools claim one code: neither is guessed
            db.get(School, school_id).parakh_udise = "09999999999"
            db.commit()
        assert name("09999999999") is None
        with SessionLocal() as db:
            db.get(School, school_id).parakh_udise = None
            db.commit()
    finally:
        with SessionLocal() as db:
            other = db.query(School).filter_by(udise_code="44444444402").one()
            db.query(RegisterStudentData).filter_by(school_id=other.id).delete()
            db.query(RegisterStudent).filter_by(school_id=other.id).delete()
            other.parakh_udise = None
            db.commit()


def test_the_fetch_keeps_the_udise_code_parakh_files_the_schools_cards_under(world):
    _, _, _, school_id = world
    from backend.models.entities import School
    with SessionLocal() as db:
        assert db.get(School, school_id).parakh_udise == "01010101010"          # from the cards read at the fetch


def test_udise_never_refills_a_name_the_school_emptied_and_never_beats_the_cards_own_name(world, monkeypatch):
    """Review H1/H2: a name emptied by an upload stays empty; a name only from UDISE+ is not sent over the name a
    teacher already put on the PARAKH card."""
    import json
    client, h, _, school_id = world
    from backend.hpc import sync
    from backend.models.register import RegisterStudent
    with SessionLocal() as db:
        regs = db.query(RegisterStudent).filter_by(school_id=school_id).order_by(RegisterStudent.student_name).all()
        emptied, from_udise = regs[0], regs[1]
        db.add(RegisterStudentData(school_id=school_id, student_id=emptied.id, session="2627", father_name=None,
                                   sources={"father_name": "import:abc"}))
        db.commit()
        people = [(r.student_name, r.apaar_id, r.parakh_student_id) for r in (emptied, from_udise)]
    full = {"fetched_at": "2026-11-01T00:00:00Z", "students": [
        {"general": {"studentId": i, "studentName": n, "apaarId": a, "fatherName": "UDISE FATHER", "motherName": ""}}
        for i, (n, a, _) in enumerate(people)]}
    monkeypatch.setattr("backend.services.sdms_data.load", lambda sid: full)
    register_data.fill_from_udise(school_id)
    with SessionLocal() as db:
        assert db.query(RegisterStudentData).filter_by(student_id=emptied.id).one().father_name is None
        assert db.query(RegisterStudentData).filter_by(student_id=from_udise.id).one().father_name == "UDISE FATHER"
    gen = [""] * 26
    gen[23], gen[24] = "GUARDIAN", "Gh. Mohd (Uncle)"                           # typed on PARAKH, not importable
    record = {"sch_info": {}, "stu_info": {"school_cur_ay_code": "2627"}}
    on_card = sync.StudentData(people[1][2], record, {"part_a1": json.dumps({"gen": gen})})
    blank = sync.StudentData(people[1][2], record, {"part_a1": json.dumps({"gen": [""] * 26})})
    with register_data.acting_school(school_id):
        assert "a1_guardian_name" not in sync.school_values("Preparatory", on_card)   # the card's own name stays
        assert sync.school_values("Preparatory", blank)["a1_guardian_name"] == "UDISE FATHER"   # an empty card gets it


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


def test_levels_from_the_schools_summative_marks(world):
    client, h, _, school_id = world
    _settings(client, h)                                                            # max 100 in every subject
    wb = _book(client, h)
    ws = wb["Preparatory"]
    sid = ws.cell(row=3, column=2).value
    ws.cell(row=3, column=28, value=80)                                              # R1: 80%
    ws.cell(row=3, column=30, value=40)                                              # Maths: 40%
    check = _upload(client, h, wb).json()
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True})
    levels = register_data.levels_from_marks(school_id, "Preparatory", "2627", [sid, "500099"])
    assert levels[sid]["PSLS1"] == "Advanced" and levels[sid]["PSLS3"] == "Beginner"
    assert levels[sid]["PSLS2"] == "Proficient" and levels[sid]["PSLS7"] == "Proficient"   # no marks: the average, 60%
    assert "500099" not in levels                                                    # no marks: random in the mix
    assert [register_data.level_for(p) for p in (75, 74.9, 50, 49.9)] == ["Advanced", "Proficient", "Proficient", "Beginner"]


def test_every_cell_of_the_school_data_sheet_has_a_border(world):
    """The cream fill of the columns to fill in hides Excel's gridlines: each cell carries its own border."""
    client, h, *_ = world
    _settings(client, h)
    ws = _book(client, h)["Preparatory"]
    sides = ("left", "right", "top", "bottom")
    bare = [c.coordinate for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column) for c in row
            if type(c).__name__ != "MergedCell" and not all(getattr(c.border, s).style == "thin" for s in sides)]
    assert ws.max_row == 102 and bare == []
    assert ws["L3"].fill.fgColor.rgb.endswith("FFFBEB")          # a fill-in cell keeps its colour, now with a border


def test_max_marks_are_50_until_the_school_sets_its_own(world):
    client, h, *_ = world
    got = client.get(f"{API}/school/register/settings", headers=h, params={"stage": "Preparatory"}).json()
    assert set(got["values"]["max_marks"].values()) == {50}


def test_dummy_fill_fills_only_empty_cells_inside_the_range_each_student_their_own(world):
    client, h, _, school_id = world
    days = _settings(client, h)                                   # max marks 100; April 20 days, June 0
    url = f"{API}/school/register/data/dummy-fill"
    body = {"stage": "Preparatory", "attendance": {"low": 70, "high": 95}, "marks": {"low": 25, "high": 45}}
    preview = client.post(url, headers=h, json=body).json()
    assert preview["applied"] is False and preview["students"] == 100
    assert preview["months"] == 100 * sum(1 for d in days if d) and preview["marks"] == 100 * 6
    with SessionLocal() as db:
        assert db.query(RegisterStudentData).filter_by(school_id=school_id).count() == 0     # a preview saves nothing

    # one student already has April and R1 from the school's own sheet: those stay
    wb = _book(client, h)
    ws = wb["Preparatory"]
    keep_id = ws.cell(row=3, column=1).value
    ws.cell(row=3, column=12, value=11)                           # April present
    ws.cell(row=3, column=28, value=7)                            # R1 marks
    check = _upload(client, h, wb).json()
    assert client.post(f"{API}/school/register/data/apply", headers=h,
                       json={"import_id": check["id"], "confirm": True}).status_code == 200

    done = client.post(url, headers=h, json={**body, "apply": True}).json()
    assert done["applied"] is True and done["students"] == 100
    with SessionLocal() as db:
        rows = db.query(RegisterStudentData).filter_by(school_id=school_id, session="2627").all()
    assert len(rows) == 100
    kept = next(r for r in rows if r.student_id == keep_id)
    assert kept.present[0] == 11 and kept.marks["1"] == 7          # what the school entered is never replaced
    for r in rows:
        for i, wd in enumerate(days):
            if not wd:
                assert r.present[i] is None                         # a month without working days stays empty
            elif r.student_id != keep_id or i:
                assert round(wd * 0.70) - 1 <= r.present[i] <= wd * 0.95
        for n, m in r.marks.items():
            if r.student_id != keep_id or n != "1":
                assert 25 <= m <= 45
    assert len({tuple(r.present) for r in rows}) > 10             # mixed: not the same numbers for everyone
    again = client.post(url, headers=h, json={**body, "apply": True}).json()
    assert again["students"] == 0                                 # nothing empty is left: nothing changes


def test_dummy_marks_never_go_above_the_subjects_max_marks(world):
    client, h, _, school_id = world
    days = [20] + [None] * 11
    client.put(f"{API}/school/register/settings", headers=h, json={"stage": "Preparatory", "values": {
        "working_days": days, "max_marks": {str(n): 30 for n in range(1, 7)}}})
    client.post(f"{API}/school/register/data/dummy-fill", headers=h,
                json={"marks": {"low": 25, "high": 45}, "apply": True})
    with SessionLocal() as db:
        marks = [m for r in db.query(RegisterStudentData).filter_by(school_id=school_id) for m in r.marks.values()]
    assert marks and max(marks) <= 30 and min(marks) >= 25


def test_dummy_fill_needs_a_sensible_range(world):
    client, h, *_ = world
    url = f"{API}/school/register/data/dummy-fill"
    assert client.post(url, headers=h, json={}).status_code in (400, 409, 422)
    bad = client.post(url, headers=h, json={"attendance": {"low": 90, "high": 60}})
    assert bad.status_code in (400, 409, 422) and "range" in bad.text.lower()


def test_deleted_columns_are_refused_not_read_shifted(world):
    """A school deleted the parents' and month columns: the marks must never be read as days present."""
    client, h, _, _ = world
    _settings(client, h)
    wb = _book(client, h)
    ws = wb["Preparatory"]
    ws.delete_cols(10, 2 + 12 + 4)                    # Name on the card, mother/guardian, 12 months, worked out
    r = _upload(client, h, wb)
    assert r.status_code == 422, r.text
    assert "deleted or moved" in r.text and "Name on the HPC card" in r.text


def test_changed_working_days_or_max_marks_in_headings_are_fine(world):
    client, h, _, _ = world
    _settings(client, h)
    wb = _book(client, h)
    client.put(f"{API}/school/register/settings", headers=h, json={"stage": "Preparatory", "values": {
        "working_days": [21] * 12, "max_marks": {str(n): 50 for n in range(1, 7)}}})
    assert _upload(client, h, wb).status_code == 200


def test_dummy_fill_replace_overwrites_a_wrong_upload_and_empties_months_without_working_days(world):
    client, h, _, school_id = world
    days = _settings(client, h)                                   # June (index 2) has 0 working days
    wb = _book(client, h)
    ws = wb["Preparatory"]
    wrong_id = ws.cell(row=3, column=1).value
    ws.cell(row=3, column=12, value=3)                            # April present: wrong
    ws.cell(row=3, column=28, value=99)                           # R1 marks: wrong
    check = _upload(client, h, wb).json()
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True})
    with SessionLocal() as db:                                    # a wrong value in a month with no working days
        d = db.query(RegisterStudentData).filter_by(school_id=school_id, student_id=wrong_id).first()
        d.present = [3, None, 27] + [None] * 9
        db.commit()
    body = {"stage": "Preparatory", "attendance": {"low": 80, "high": 90}, "marks": {"low": 30, "high": 40},
            "apply": True, "replace": True}
    client.post(f"{API}/school/register/data/dummy-fill", headers=h, json=body)
    with SessionLocal() as db:
        d = db.query(RegisterStudentData).filter_by(school_id=school_id, student_id=wrong_id).first()
        present, marks = list(d.present), dict(d.marks)
    assert round(days[0] * 0.8) - 1 <= present[0] <= days[0] * 0.9 and present[2] is None
    assert 30 <= marks["1"] <= 40


def _marks_book(client, h):
    r = client.get(f"{API}/school/register/marks.xlsx", headers=h)
    assert r.status_code == 200, r.text
    return load_workbook(io.BytesIO(r.content))


def test_marks_workbook_has_only_the_student_and_the_summative_marks(world):
    client, h, _, _ = world
    _settings(client, h)
    wb = _marks_book(client, h)
    ws = wb["Preparatory"]
    heads = [c.value for c in ws[2]]
    assert heads[:3] == ["Register ID", "PARAKH ID", "Student name (PARAKH)"]
    assert not any("present" in str(x) or "Father" in str(x) for x in heads)        # no attendance, no parents
    assert any(str(x).startswith("Language 1") for x in heads) and len(heads) == 8 + 6
    assert "Foundational" not in wb.sheetnames                                      # no summative marks there


def test_marks_upload_changes_only_marks_and_keeps_attendance_and_parents(world):
    client, h, _, school_id = world
    _settings(client, h)
    full = _book(client, h)                                       # attendance and a parent from the full workbook
    ws = full["Preparatory"]
    sid = ws.cell(row=3, column=1).value
    ws.cell(row=3, column=9, value="ABDUL RASHID")
    ws.cell(row=3, column=12, value=18)
    ws.cell(row=3, column=28, value=60)                           # R1 marks 60
    ws.cell(row=3, column=29, value=55)                           # R2 marks 55
    check = _upload(client, h, full).json()
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": check["id"], "confirm": True})

    wb = _marks_book(client, h)
    ms = wb["Preparatory"]
    assert ms.cell(row=3, column=1).value == sid and ms.cell(row=3, column=9).value == 60   # today's marks shown
    ms.cell(row=3, column=9, value=72)                            # R1 changed
    ms.cell(row=3, column=10, value=None)                         # R2 left empty: kept
    ms.cell(row=4, column=11, value=101)                          # above the max (100): a problem
    res = _upload(client, h, wb, name="School_Marks.xlsx").json()
    assert res["summary"]["kind"] == "marks" and res["summary"]["problem"] == 1 and res["summary"]["ready"] == 1
    client.post(f"{API}/school/register/data/apply", headers=h, json={"import_id": res["id"], "confirm": True})
    with SessionLocal() as db:
        d = db.query(RegisterStudentData).filter_by(school_id=school_id, student_id=sid).first()
        assert d.marks["1"] == 72 and d.marks["2"] == 55                              # R2 kept
        assert d.present[0] == 18 and d.father_name == "ABDUL RASHID"                 # untouched
