"""Small low-risk fixes from the audit (L-2, L-5). Made-up schools and teachers only."""
import uuid

from fastapi.testclient import TestClient

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


def _school(client):
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    body = {"udise_code": udise, "school_name": f"Secret Name School {tag}", "state": "Test", "district": "Test",
            "admin_name": "Admin", "admin_email": f"a.{tag}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=body).status_code == 201
    return body, tag


def test_registering_a_taken_udise_does_not_show_the_other_schools_name():
    from backend.main import app
    client = TestClient(app)
    client.headers.update(HDR)
    body, tag = _school(client)
    again = client.post(f"{API}/auth/school/register", json={**body, "admin_email": f"other.{tag}@example.com"})
    assert again.status_code == 409 and body["school_name"] not in again.text
    same_email = client.post(f"{API}/auth/school/register", json={**body, "udise_code": "1" + body["udise_code"][1:]
                                                                  if body["udise_code"][0] != "1" else "2" + body["udise_code"][1:]})
    assert same_email.status_code == 409 and body["admin_email"] not in same_email.text


def test_a_teacher_without_grade_or_section_is_not_shown_an_invented_one():
    from backend.main import app
    client = TestClient(app)
    client.headers.update(HDR)
    body, tag = _school(client)
    client.post(f"{API}/auth/login", json={"identifier": body["udise_code"], "password": "secret123"})
    from backend.database import SessionLocal
    from backend.models.entities import Teacher
    made = client.post(f"{API}/school/teachers", json={"teacher_name": "Plain Teacher", "username": f"plain{tag}",
                                                       "password": "secret123", "assigned_stages": ["Middle"]}).json()
    with SessionLocal() as db:                                # an account made before grades were asked for
        t = db.get(Teacher, made["id"])
        t.assigned_grade, t.assigned_section = "", ""
        db.commit()
    listed = next(t for t in client.get(f"{API}/school/teachers").json() if t["id"] == made["id"])
    assert listed["assigned_grade"] in ("", None) and listed["assigned_grades"] == []
    assert listed["assigned_section"] in ("", None)
