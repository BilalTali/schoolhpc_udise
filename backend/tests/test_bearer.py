"""M-2: the old Bearer login, until it ends on 2026-11-02 - 24 hours at most, ended by logout and by a password
change. A password change also ends the account's cookie sessions. Made-up accounts only."""
import uuid
from datetime import date

import jwt
import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


@pytest.fixture
def bearer_still_on(monkeypatch):
    """These tests are about the old login while it exists; they must not start failing on 2026-11-02."""
    from backend import config
    monkeypatch.setattr(config, "BEARER_LAST_DAY", date(2999, 1, 1))


def _accounts():
    from backend.main import app
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    admin = TestClient(app)
    admin.headers.update(HDR)
    admin.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Bearer School", "state": "Test",
               "district": "Test", "admin_name": "Admin", "admin_email": f"b.{tag}@example.com", "password": "secret123"})
    admin.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"})
    tid = admin.post(f"{API}/school/teachers", json={"teacher_name": "Bearer Teacher", "username": f"bearer{tag}",
                     "password": "secret123", "assigned_stages": ["Preparatory"]}).json()["id"]
    return admin, f"bearer{tag}", tid


def _bearer(client, username, password="secret123"):
    return client.post(f"{API}/auth/login", json={"identifier": username, "password": password}).json()["access_token"]


def test_a_bearer_token_lasts_24_hours_at_most(bearer_still_on):
    from backend.config import JWT_ALGORITHM, JWT_SECRET
    from backend.main import app
    _, username, _ = _accounts()
    token = _bearer(TestClient(app), username)
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert claims["exp"] - claims["iat"] <= 24 * 3600


def test_logout_ends_the_bearer_token(bearer_still_on):
    from backend.main import app
    _, username, _ = _accounts()
    client = TestClient(app)
    token = _bearer(client, username)
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{API}/auth/me", headers=auth).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=auth).status_code == 200
    assert TestClient(app).get(f"{API}/auth/me", headers=auth).status_code == 401
    fresh = _bearer(TestClient(app), username)                       # signing in again works at once
    assert TestClient(app).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_a_password_change_ends_every_session_of_that_teacher(bearer_still_on):
    from backend.main import app
    admin, username, tid = _accounts()
    token = _bearer(TestClient(app), username)
    browser = TestClient(app)
    browser.headers.update(HDR)
    browser.post(f"{API}/auth/login", json={"identifier": username, "password": "secret123"})
    assert browser.get(f"{API}/auth/me").status_code == 200
    assert admin.put(f"{API}/school/teachers/{tid}", json={"password": "newsecret123"}).status_code == 200
    assert TestClient(app).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert browser.get(f"{API}/auth/me").status_code == 401                 # the 15-minute cookie
    assert browser.post(f"{API}/auth/refresh").status_code == 401           # and its refresh token
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": username, "password": "newsecret123"}).status_code == 200


def test_the_bearer_login_ends_after_its_last_day(monkeypatch):
    from backend import config
    from backend.main import app
    _, username, _ = _accounts()
    monkeypatch.setattr(config, "BEARER_LAST_DAY", date(2999, 1, 1))
    token = _bearer(TestClient(app), username)
    monkeypatch.setattr(config, "BEARER_LAST_DAY", date(2000, 1, 1))
    client = TestClient(app)
    login = client.post(f"{API}/auth/login", json={"identifier": username, "password": "secret123"})
    assert login.status_code == 200 and login.json()["access_token"] == ""          # no new Bearer tokens
    assert client.get(f"{API}/auth/me").status_code == 200                          # the cookie session works
    assert TestClient(app).get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_the_last_day_is_1_november_2026():
    from backend import config
    assert config.BEARER_LAST_DAY == date(2026, 11, 1)
