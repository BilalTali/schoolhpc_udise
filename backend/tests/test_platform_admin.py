"""The application admin: one account above every school. Made-up schools, teachers and activities only."""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import session_headers

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}
LOGIN, PASSWORD = "appadmin", "a-long-app-admin-secret"


@pytest.fixture
def platform(monkeypatch):
    from backend import config
    from backend.database import SessionLocal
    from backend.main import app
    from backend.models.entities import PlatformAdmin
    from backend.routers import auth
    monkeypatch.setattr(config, "APP_ADMIN_LOGIN", LOGIN)
    monkeypatch.setattr(auth, "_address", lambda request: "127.0.0.1")        # a browser on the server PC
    with SessionLocal() as db:
        db.query(PlatformAdmin).delete()
        db.commit()
    schools = []
    for name in ("North", "South"):
        tag = uuid.uuid4().hex[:8]
        udise = str(int(tag, 16) % 10**11).zfill(11)
        c = TestClient(app)
        c.headers.update(HDR)
        assert c.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": f"{name} School {tag}",
                      "state": "Test", "district": "Test", "admin_name": "Admin", "admin_email": f"{name}.{tag}@example.com",
                      "password": "secret123"}).status_code == 201
        c.headers.update(session_headers(udise)[0])
        tid = c.post(f"{API}/school/teachers", json={"teacher_name": f"{name} Teacher", "username": f"{name.lower()}{tag}",
                     "password": "secret123", "assigned_stages": ["Preparatory"]}).json()["id"]
        schools.append({"admin": c, "udise": udise, "teacher": f"{name.lower()}{tag}", "teacher_id": tid,
                        "id": c.get(f"{API}/auth/me").json()["id"]})
    return app, schools


def _app_admin(app):
    c = TestClient(app)
    c.headers.update(HDR)
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": LOGIN, "password": PASSWORD}).status_code == 200
    assert c.post(f"{API}/auth/login", json={"identifier": LOGIN, "password": PASSWORD}).json()["role"] == "APP_ADMIN"
    return c


def test_the_password_is_set_once_and_only_from_the_server_pc(platform, monkeypatch):
    from backend.routers import auth
    app, _ = platform
    c = TestClient(app)
    c.headers.update(HDR)
    first = c.post(f"{API}/auth/login", json={"identifier": LOGIN, "password": "anything"})
    assert first.status_code == 409 and first.json()["detail"]["setup_required"] is True
    monkeypatch.setattr(auth, "_address", lambda request: "192.168.1.20")       # another device on the network
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": LOGIN, "password": PASSWORD}).status_code == 403
    monkeypatch.setattr(auth, "_address", lambda request: "127.0.0.1")
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": "someoneelse", "password": PASSWORD}).status_code == 403
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": LOGIN, "password": "short"}).status_code == 422
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": LOGIN, "password": PASSWORD}).status_code == 200
    assert c.post(f"{API}/auth/app-admin/setup", json={"login": LOGIN, "password": "another-long-one-123"}).status_code == 409
    assert c.post(f"{API}/auth/login", json={"identifier": LOGIN, "password": "wrong-password-here"}).status_code == 401
    assert c.post(f"{API}/auth/login", json={"identifier": LOGIN, "password": PASSWORD}).status_code == 200
    assert c.get(f"{API}/auth/me").json()["role"] == "APP_ADMIN"


def test_only_the_application_admin_reaches_the_platform_pages(platform):
    app, schools = platform
    admin = _app_admin(app)
    assert admin.get(f"{API}/platform/stats").status_code == 200
    assert schools[0]["admin"].get(f"{API}/platform/schools").status_code == 403
    teacher = TestClient(app)
    teacher.headers.update(session_headers(schools[0]["teacher"])[0])
    assert teacher.get(f"{API}/platform/schools").status_code == 403
    assert admin.get(f"{API}/school/teachers").status_code == 403                    # not a school admin
    assert admin.post(f"{API}/activity-library/sync", json={}).status_code == 403     # schools update from PARAKH


def test_every_school_and_teacher_is_listed_and_can_be_switched_off_and_on(platform):
    app, schools = platform
    admin = _app_admin(app)
    listed = {s["id"]: s for s in admin.get(f"{API}/platform/schools").json()}
    north = schools[0]
    assert north["id"] in listed and listed[north["id"]]["teachers"] == 1
    teachers = admin.get(f"{API}/platform/schools/{north['id']}/teachers").json()
    assert [t["username"] for t in teachers] == [north["teacher"]]

    t_session = session_headers(north["teacher"])[0]
    assert admin.put(f"{API}/platform/schools/{north['id']}", json={"is_active": False}).status_code == 200
    assert north["admin"].get(f"{API}/auth/me").status_code == 401                   # the school admin is signed out
    assert TestClient(app).get(f"{API}/auth/me", headers=t_session).status_code == 401   # and its teachers
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": north["teacher"], "password": "secret123"}).status_code in (401, 403)
    assert admin.put(f"{API}/platform/schools/{north['id']}", json={"is_active": True}).status_code == 200
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": north["teacher"], "password": "secret123"}).status_code == 200


def test_a_forgotten_password_is_replaced_and_old_sessions_end(platform):
    app, schools = platform
    admin = _app_admin(app)
    south = schools[1]
    old = session_headers(south["teacher"])[0]
    assert admin.post(f"{API}/platform/teachers/{south['teacher_id']}/password", json={"password": "short"}).status_code == 422
    assert admin.post(f"{API}/platform/teachers/{south['teacher_id']}/password", json={"password": "brand-new-123"}).status_code == 200
    assert TestClient(app).get(f"{API}/auth/me", headers=old).status_code == 401
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": south["teacher"], "password": "brand-new-123"}).status_code == 200
    assert admin.post(f"{API}/platform/schools/{south['id']}/password", json={"password": "school-new-123"}).status_code == 200
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": south["udise"], "password": "school-new-123"}).status_code == 200
    trail = admin.get(f"{API}/platform/audit", params={"school_id": south["id"]}).json()
    assert {"set_teacher_password", "set_school_password"} <= {r["action"] for r in trail}
    assert "brand-new-123" not in str(trail)                                       # never the password


def test_the_dashboard_counts_every_school(platform):
    app, schools = platform
    admin = _app_admin(app)
    s = admin.get(f"{API}/platform/stats").json()
    assert s["schools"] >= 2 and s["teachers"] >= 2 and "cards_saved" in s and "activities_waiting" in s


def test_activities_are_offered_to_every_school_only_after_the_application_admin_says_so(platform):
    app, schools = platform
    admin = _app_admin(app)
    rubric = {a: {"beginner": f"{a} b", "proficient": f"{a} p", "advanced": f"{a} a"} for a in ("awareness", "sensitivity", "creativity")}
    body = {"stage": "Preparatory", "title": f"Platform story {uuid.uuid4().hex[:6]}", "activity_text": "Children retell a story.",
            "assessment_text": "Can you tell it again?", "rubric": rubric, "grade_id": 7, "subjects": ["PSLS1"],
            "goals": ["L1CG1"], "competencies": ["L1C1.1"]}
    made = admin.post(f"{API}/activity-library", json=body)
    assert made.status_code in (200, 201), made.text
    aid = made.json()["id"]
    north_teacher = session_headers(schools[0]["teacher"])[0]
    library = lambda: {i["id"] for i in TestClient(app).get(f"{API}/activity-library", headers=north_teacher,
                                                             params={"stage": "Preparatory", "page_size": 500}).json()["items"]}
    assert aid not in library()                                                    # not offered yet
    assert admin.post(f"{API}/platform/activities/{aid}/offer").status_code == 200
    assert aid in library()                                                        # every school now
    assert next(a for a in admin.get(f"{API}/platform/activities").json() if a["id"] == aid)["state"] == "offered"
    assert admin.post(f"{API}/platform/activities/{aid}/withdraw").status_code == 200
    assert aid not in library()
