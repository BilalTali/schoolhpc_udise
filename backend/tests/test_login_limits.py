"""H-8: guessing app passwords is slowed down (growing delay, not a lockout), and new passwords are 8+ characters."""
import uuid

import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


@pytest.fixture
def clock(monkeypatch):
    from backend.services import login_limits
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(login_limits, "_clock", lambda: now["t"])
    login_limits.reset()
    yield now
    login_limits.reset()


@pytest.fixture
def school():
    from backend.main import app
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    client = TestClient(app)
    client.headers.update(HDR)
    assert client.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Limit School", "state": "Test",
                       "district": "Test", "admin_name": "Limit Admin", "admin_email": f"lim.{tag}@example.com",
                       "password": "secret123"}).status_code == 201
    return client, udise, tag


def _login(client, who, password):
    return client.post(f"{API}/auth/login", json={"identifier": who, "password": password})


def test_five_wrong_passwords_then_a_growing_wait(clock, school):
    client, udise, _ = school
    for _ in range(5):
        assert _login(client, udise, "wrong-pass").status_code == 401
    r = _login(client, udise, "secret123")                       # even the right password waits now
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and "try again in" in r.json()["detail"].lower()
    first_wait = int(r.headers["Retry-After"])
    clock["t"] += first_wait
    assert _login(client, udise, "wrong-pass").status_code == 401   # allowed again after the wait ...
    r = _login(client, udise, "wrong-pass")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > first_wait   # ... and the next wait is longer
    clock["t"] += 16 * 60                                         # 15 minutes later the slate is clean
    assert _login(client, udise, "secret123").status_code == 200


def test_a_right_password_clears_the_count(clock, school):
    client, udise, _ = school
    for _ in range(4):
        _login(client, udise, "wrong-pass")
    assert _login(client, udise, "secret123").status_code == 200
    for _ in range(4):
        assert _login(client, udise, "wrong-pass").status_code == 401


def test_one_username_waiting_does_not_slow_others_on_the_same_network(clock, school):
    client, udise, tag = school
    for _ in range(6):
        _login(client, udise, "wrong-pass")
    assert _login(client, f"nobody{tag}", "wrong-pass").status_code == 401   # another name: not slowed by this one


def test_a_whole_network_guessing_many_names_is_slowed_too(clock, school):
    from backend.services import login_limits
    client, udise, tag = school
    for i in range(login_limits.PER_ADDRESS):
        assert _login(client, f"guess{i}{tag}", "wrong-pass").status_code == 401
    assert _login(client, udise, "secret123").status_code == 429


def test_new_and_reset_passwords_need_8_characters(clock, school):
    client, udise, tag = school
    assert _login(client, udise, "secret123").status_code == 200
    short = client.post(f"{API}/school/teachers", json={"teacher_name": "Short", "username": f"short{tag}", "password": "1234567"})
    assert short.status_code == 422
    made = client.post(f"{API}/school/teachers", json={"teacher_name": "Long", "username": f"long{tag}", "password": "12345678"})
    assert made.status_code == 201
    reset = client.put(f"{API}/school/teachers/{made.json()['id']}", json={"password": "short12"})
    assert reset.status_code == 422                               # no longer silently ignored
    assert client.put(f"{API}/school/teachers/{made.json()['id']}", json={"password": "longer123"}).status_code == 200
    other = uuid.uuid4().hex[:8]
    assert client.post(f"{API}/auth/school/register", json={"udise_code": str(int(other, 16) % 10**11).zfill(11),
                       "school_name": "Short School", "state": "Test", "district": "Test", "admin_name": "Short Admin",
                       "admin_email": f"s.{other}@example.com", "password": "1234567"}).status_code == 422
