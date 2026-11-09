"""The portal's access key: set by the app admin; every browser enters it before using the portal."""
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app
from backend.services import access_key, login_limits

API = "/api/v1"
ADMIN = "portaladmin"


@pytest.fixture
def admin(monkeypatch):
    """The admin's login and password kept in .env (no first-sign-in setup)."""
    monkeypatch.setattr(config, "APP_ADMIN_LOGIN", ADMIN)
    monkeypatch.setattr(config, "APP_ADMIN_PASSWORD", "Env-Admin-Pass1")
    access_key.clear()
    login_limits.reset()
    c = TestClient(app)
    r = c.post(f"{API}/auth/login", json={"identifier": ADMIN, "password": "Env-Admin-Pass1"})
    assert r.status_code == 200 and r.json()["role"] == "APP_ADMIN", r.text
    yield c
    access_key.clear()
    login_limits.reset()


def test_the_admin_signs_in_with_the_password_from_env_only(admin):
    other = TestClient(app)
    assert other.post(f"{API}/auth/login", json={"identifier": ADMIN, "password": "wrong-pass"}).status_code == 401


def test_without_a_key_the_portal_is_open(admin):
    c = TestClient(app)
    assert c.get(f"{API}/access/status").json() == {"required": False, "granted": True}
    assert c.get(f"{API}/auth/me").status_code == 401                 # open: the normal sign-in answers


def test_once_the_admin_sets_a_key_every_browser_must_enter_it(admin):
    h = {"X-Requested-With": "TeacherAssist"}
    assert admin.put(f"{API}/platform/access-key", headers=h, json={"key": "kashmir-2026"}).json()["set"] is True
    assert admin.get(f"{API}/auth/me").status_code == 200             # the admin's own browser stays unlocked

    visitor = TestClient(app)
    assert visitor.get(f"{API}/access/status").json() == {"required": True, "granted": False}
    blocked = visitor.post(f"{API}/auth/login", json={"identifier": "anyone", "password": "x"})
    assert blocked.status_code == 403 and blocked.json()["detail"]["access_key"] is True     # even signing in waits
    assert visitor.post(f"{API}/access/unlock", json={"key": "wrong"}).status_code == 403
    assert visitor.post(f"{API}/access/unlock", json={"key": " kashmir-2026 "}).status_code == 200
    assert visitor.get(f"{API}/access/status").json()["granted"] is True
    assert visitor.post(f"{API}/auth/login", json={"identifier": "anyone", "password": "x"}).status_code == 401

    # a new key: every browser enters it again
    admin.put(f"{API}/platform/access-key", headers=h, json={"key": "new-key-2027"})
    assert visitor.get(f"{API}/auth/me").status_code == 403
    assert access_key.check("new-key-2027") and not access_key.check("kashmir-2026")


def test_the_key_is_stored_hashed_and_only_the_admin_sets_it(admin):
    h = {"X-Requested-With": "TeacherAssist"}
    admin.put(f"{API}/platform/access-key", headers=h, json={"key": "kashmir-2026"})
    assert "kashmir-2026" not in access_key._path().read_text()
    assert admin.put(f"{API}/platform/access-key", headers=h, json={"key": "123"}).status_code == 422   # too short
    visitor = TestClient(app)
    visitor.post(f"{API}/access/unlock", json={"key": "kashmir-2026"})
    assert visitor.put(f"{API}/platform/access-key", headers=h, json={"key": "taken-over"}).status_code in (401, 403)


def test_wrong_keys_slow_down(admin):
    admin.put(f"{API}/platform/access-key", headers={"X-Requested-With": "TeacherAssist"}, json={"key": "kashmir-2026"})
    visitor = TestClient(app)
    codes = [visitor.post(f"{API}/access/unlock", json={"key": f"guess{i}"}).status_code for i in range(12)]
    assert 429 in codes
