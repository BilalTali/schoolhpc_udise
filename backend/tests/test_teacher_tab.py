"""The school opens a teacher in a second tab: the teacher tab has its own session, the school's tab keeps its own.

The school also saves the teacher's PARAKH login (encrypted) so the teacher tab connects with one captcha.
"""
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models.entities import Teacher
from backend.tests.conftest import session_headers

API = "/api/v1"


def _school(code, admin_email):
    c = TestClient(app)
    school = {"udise_code": code, "school_name": f"School {code}", "state": "Jammu and Kashmir", "district": "Budgam",
              "admin_name": "Admin", "admin_email": admin_email, "password": "secret123"}
    assert c.post(f"{API}/auth/school/register", json=school).status_code == 201
    h, _ = session_headers(code)
    return c, h


def _teacher(c, h, username):
    r = c.post(f"{API}/school/teachers", headers=h, json={"teacher_name": f"Teacher {username}", "username": username,
                                                           "password": "secret123", "assigned_stages": ["Preparatory"]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_school_saves_a_teachers_parakh_login_encrypted_and_only_for_its_own_teachers():
    c, h = _school("02000000001", "a1@example.com")
    tid = _teacher(c, h, "tabteach1")
    r = c.put(f"{API}/school/teachers/{tid}/parakh-login", headers=h,
              json={"hpc_login_id": "9906000001", "hpc_password": "Parakh@123"})
    assert r.status_code == 200 and r.json()["has_parakh_login"] is True and "Parakh@123" not in r.text
    with SessionLocal() as db:
        t = db.get(Teacher, tid)
        assert t.hpc_login_id == "9906000001" and t.hpc_password == "Parakh@123"
        assert "Parakh@123" not in (t.hpc_password_encrypted or "")                 # stored encrypted
    _, other = _school("02000000002", "a2@example.com")
    assert c.put(f"{API}/school/teachers/{tid}/parakh-login", headers=other,
                 json={"hpc_login_id": "x123", "hpc_password": "y123"}).status_code == 404


def test_the_teacher_tab_and_the_school_tab_keep_their_own_sessions():
    c, h = _school("02000000003", "a3@example.com")
    tid = _teacher(c, h, "tabteach2")
    browser = TestClient(app)                                  # one browser: both tabs share its cookie jar
    browser.cookies.set("ta_access", h["Cookie"].split("=", 1)[1], path="/api")
    opened = browser.post(f"{API}/school/teachers/{tid}/open-tab", headers={"X-Requested-With": "TeacherAssist"})
    assert opened.status_code == 200 and opened.json()["tab"] == f"teacher:{tid}"
    assert browser.cookies.get("ta_access_t")

    teacher_tab = {"X-TA-Tab": f"teacher:{tid}", "X-Requested-With": "TeacherAssist"}
    assert browser.get(f"{API}/auth/me", headers=teacher_tab).json()["id"] == tid               # tab 2: the teacher
    assert browser.get(f"{API}/auth/me").json()["role"] == "SCHOOL_ADMIN"                     # tab 1: still the school

    # a tab that says it is another teacher is refused, never mixed up
    wrong = browser.get(f"{API}/auth/me", headers={"X-TA-Tab": "teacher:someone-else"})
    assert wrong.status_code == 401 and "another teacher" in wrong.json()["detail"]

    # the teacher tab renews only its own cookies
    renewed = browser.post(f"{API}/auth/refresh", headers=teacher_tab)
    assert renewed.status_code == 200
    assert browser.get(f"{API}/auth/me", headers=teacher_tab).json()["id"] == tid

    # signing out in the teacher tab leaves the school signed in
    assert browser.post(f"{API}/auth/logout", headers=teacher_tab).status_code == 200
    assert browser.get(f"{API}/auth/me", headers=teacher_tab).status_code == 401
    assert browser.get(f"{API}/auth/me").json()["role"] == "SCHOOL_ADMIN"


def test_only_the_school_of_the_teacher_can_open_its_tab():
    c, h = _school("02000000004", "a4@example.com")
    tid = _teacher(c, h, "tabteach3")
    _, other = _school("02000000005", "a5@example.com")
    assert c.post(f"{API}/school/teachers/{tid}/open-tab", headers=other).status_code == 404
    th, _ = session_headers("tabteach3")
    assert c.post(f"{API}/school/teachers/{tid}/open-tab", headers=th).status_code in (401, 403)
