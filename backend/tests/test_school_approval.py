"""Only the app admin lets a new school in: a school that registers itself waits (PENDING) and cannot sign in
until approved; a rejected one cannot sign in either. Schools registered before approvals began stay approved."""
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models.entities import School
from backend.routers import auth as auth_router

API = "/api/v1"


from backend.tests.test_platform_admin import HDR, _app_admin, platform  # noqa: F401  (the fixture)


def _register(client, udise):
    with SessionLocal() as db:
        db.query(School).filter_by(udise_code=udise).delete()
        db.commit()
    body = {"udise_code": udise, "school_name": "Waiting School", "state": "JK", "district": "Budgam",
            "admin_name": "Head", "admin_email": f"{udise}@example.com", "password": "secret123"}
    r = client.post(f"{API}/auth/school/register", json=body, headers=HDR)
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, udise):
    return client.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"}, headers=HDR)


def test_a_new_school_waits_for_the_app_admin_and_signs_in_once_approved(platform, monkeypatch):
    monkeypatch.setattr(auth_router, "SCHOOL_APPROVAL", True)
    client = TestClient(app)
    school = _register(client, "55555555501")
    assert school["approval"] == "PENDING"
    r = _login(client, "55555555501")
    assert r.status_code == 403 and "waiting for approval" in r.text

    admin = _app_admin(platform[0])
    rows = admin.get(f"{API}/platform/schools").json()
    assert next(s for s in rows if s["id"] == school["id"])["approval"] == "PENDING"
    assert admin.get(f"{API}/platform/stats").json()["schools_pending"] >= 1
    assert admin.post(f"{API}/platform/schools/{school['id']}/approve").status_code == 200
    assert _login(TestClient(app), "55555555501").status_code == 200


def test_a_rejected_school_cannot_sign_in_and_switching_it_on_approves_it(platform, monkeypatch):
    monkeypatch.setattr(auth_router, "SCHOOL_APPROVAL", True)
    client = TestClient(app)
    school = _register(client, "55555555502")
    admin = _app_admin(platform[0])
    assert admin.post(f"{API}/platform/schools/{school['id']}/reject").status_code == 200
    r = _login(TestClient(app), "55555555502")
    assert r.status_code == 403 and "not approved" in r.text
    on = admin.put(f"{API}/platform/schools/{school['id']}", json={"is_active": True})
    assert on.status_code == 200
    assert _login(TestClient(app), "55555555502").status_code == 200


def test_a_school_from_before_approvals_signs_in_and_approve_does_not_switch_on_a_switched_off_school(platform):
    """An empty approval (every school registered before approvals began) is approved: it signs in. Approve only
    acts on a waiting or rejected school - a school switched off on purpose stays off."""
    app, schools = platform
    with SessionLocal() as db:
        s = db.get(School, schools[0]["id"])
        s.approval = None
        db.commit()
    assert _login(TestClient(app), schools[0]["udise"]).status_code == 200
    admin = _app_admin(app)
    assert admin.put(f"{API}/platform/schools/{schools[0]['id']}", json={"is_active": False}).status_code == 200
    assert admin.post(f"{API}/platform/schools/{schools[0]['id']}/approve").status_code == 409
    with SessionLocal() as db:
        assert db.get(School, schools[0]["id"]).is_active is False
