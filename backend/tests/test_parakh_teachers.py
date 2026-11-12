"""Teacher accounts from PARAKH: login ID = PARAKH ID, the school sets only this app's password; name, code and
classes come from PARAKH. PARAKH is MOCKED here (the shapes are PARAKH's live reply of 2026-11-01)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from backend.database import SessionLocal
from backend.main import app
from backend.models.entities import Teacher
from backend.routers import schools as schools_router
from backend.tests.conftest import session_headers

API = "/api/v1"


class FakeParakh:
    state, district_id, school_id = 101, 5, 77

    def school_teachers(self):
        return [
            {"id": 41458, "staff_id": "T7AFCD2", "teacher_code": "TP48851020", "staff_fname": "BILAL AHMAD",
             "staff_lname": "TALI", "reg_in_progress": False,
             "grade_section_mapping": [{"ct": 1, "grd": 8, "sec": 1}, {"ct": 1, "grd": 9, "sec": 1}, {"ct": 0, "grd": 3, "sec": 1}]},
            {"id": 41687, "staff_id": "T28771D", "teacher_code": "TP23674243", "staff_fname": "RUKHSANA", "staff_lname": "SHAH",
             "grade_section_mapping": [{"ct": 1, "grd": 4, "sec": 1}, {"ct": 1, "grd": 6, "sec": 2}]},
            {"id": 41555, "staff_id": "T9C10AB", "teacher_code": "TP78806198", "staff_fname": "SHABIR AHMAD",
             "staff_lname": "GADDA", "grade_section_mapping": []},
        ]

    def teacher_grade_sections(self, tid):
        return []

    def _request(self, method, path, **kw):
        if path.endswith("/grades"):
            return {"data": {"FOUNDATIONAL": [{"id": 3, "grade_caption": "Balvatika 3"}, {"id": 4, "grade_caption": "Grade 1"}],
                             "PREPARATORY": [{"id": 6, "grade_caption": "Grade 3"}, {"id": 8, "grade_caption": "Grade 5"}],
                             "MIDDLE": [{"id": 9, "grade_caption": "Grade 6"}]}}
        if path.endswith("/sections"):
            return {"data": {"records": [{"id": 1, "section_caption": "A"}, {"id": 2, "section_caption": "B"}]}}
        raise AssertionError(path)


@pytest.fixture
def school(monkeypatch):
    monkeypatch.setattr(schools_router.hpc_sessions, "portal_for", lambda *a, **k: FakeParakh())
    client = TestClient(app)
    udise = "33333333301"
    body = {"udise_code": udise, "school_name": "PARAKH Teachers School", "state": "JK", "district": "Budgam",
            "admin_name": "Admin", "admin_email": f"{udise}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=body).status_code in (201, 409)
    headers, _ = session_headers(udise)
    with SessionLocal() as db:                         # a clean start: no accounts from an earlier run
        db.query(Teacher).filter(func.lower(Teacher.username).in_(["t7afcd2", "t28771d", "t9c10ab", "old_bilal"])).delete(
            synchronize_session=False)
        db.commit()
    return client, headers


def test_the_list_comes_from_parakh_with_classes_and_no_accounts_yet(school):
    client, h = school
    rows = client.get(f"{API}/school/teachers/parakh", headers=h).json()["teachers"]
    assert [r["parakh_id"] for r in rows] == ["T7AFCD2", "T28771D", "T9C10AB"]          # by name
    bilal = rows[0]
    assert bilal["name"] == "BILAL AHMAD TALI" and bilal["teacher_code"] == "TP48851020" and bilal["account"] is None
    assert [(c["grade"], c["section"], c["class_teacher"]) for c in bilal["classes"]] == [
        ("Grade 5", "A", True), ("Grade 6", "A", True), ("Balvatika 3", "A", False)]


def test_import_creates_accounts_whose_login_id_is_the_parakh_id(school):
    client, h = school
    res = client.post(f"{API}/school/teachers/parakh/import", headers=h, json={"teachers": [
        {"parakh_id": "T7AFCD2", "password": "teacher-pass-1"}, {"parakh_id": "T28771D", "password": "short"},
        {"parakh_id": "T9C10AB"}, {"parakh_id": "TNOTHERE", "password": "teacher-pass-1"}]}).json()["results"]
    assert [r["status"] for r in res] == ["created", "error", "error", "error"]
    with SessionLocal() as db:
        t = db.query(Teacher).filter_by(username="T7AFCD2").one()          # the PARAKH ID as PARAKH writes it
        assert (t.teacher_name, t.hpc_login_id, t.employee_code) == ("BILAL AHMAD TALI", "T7AFCD2", "TP48851020")
        assert (t.assigned_stage, t.assigned_grade, t.assigned_section) == ("Preparatory, Middle", "Grade 5, Grade 6", "A")
        assert t.hpc_password_encrypted is None                          # their PARAKH password is never set here
    session_headers("T7AFCD2", "teacher-pass-1")                         # signs in with the PARAKH ID, any case
    rows = client.get(f"{API}/school/teachers/parakh", headers=h).json()["teachers"]
    assert rows[0]["account"]["login_matches"] is True


def test_an_existing_account_gets_the_parakh_id_as_its_login_and_keeps_its_password(school):
    client, h = school
    client.post(f"{API}/school/teachers", headers=h, json={"teacher_name": "Bilal", "username": "old_bilal",
                                                           "password": "old-password-1", "assigned_stages": ["Middle"]})
    with SessionLocal() as db:
        t = db.query(Teacher).filter_by(username="old_bilal").one()
        t.hpc_login_id = "T7AFCD2"
        db.commit()
    res = client.post(f"{API}/school/teachers/parakh/import", headers=h,
                      json={"teachers": [{"parakh_id": "T7AFCD2"}]}).json()["results"]
    assert res == [{"parakh_id": "T7AFCD2", "status": "updated", "message": "login ID is now T7AFCD2 (was old_bilal)"}]
    session_headers("t7afcd2", "old-password-1")


def test_teachers_cannot_list_or_import(school):
    client, h = school
    client.post(f"{API}/school/teachers/parakh/import", headers=h,
                json={"teachers": [{"parakh_id": "T7AFCD2", "password": "teacher-pass-1"}]})
    th, _ = session_headers("T7AFCD2", "teacher-pass-1")
    assert client.get(f"{API}/school/teachers/parakh", headers=th).status_code in (401, 403)
    assert client.post(f"{API}/school/teachers/parakh/import", headers=th,
                       json={"teachers": [{"parakh_id": "T7AFCD2", "password": "x" * 9}]}).status_code in (401, 403)
