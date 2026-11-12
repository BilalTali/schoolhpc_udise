"""Teacher login IDs keep their capitals as typed; signing in works with the ID as typed or in another case."""
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import login_limits
from backend.tests.conftest import session_headers

API = "/api/v1"


def test_a_teacher_id_keeps_its_capitals_and_signs_in_either_way():
    login_limits.reset()
    client = TestClient(app)
    client.post(f"{API}/auth/school/register", json={
        "udise_code": "66666666661", "school_name": "Case School", "state": "JK", "district": "Budgam",
        "admin_name": "Admin", "admin_email": "case@example.com", "password": "secret123"})
    h, _ = session_headers("66666666661")
    made = client.post(f"{API}/school/teachers", headers=h, json={
        "teacher_name": "Mixed Case", "username": "Sunita_RAO7", "password": "PassWord99", "assigned_stages": ["Preparatory"]})
    assert made.status_code in (200, 201), made.text
    assert made.json()["username"] == "Sunita_RAO7"                                  # not lowercased
    again = client.post(f"{API}/school/teachers", headers=h, json={
        "teacher_name": "Copy", "username": "sunita_rao7", "password": "PassWord99", "assigned_stages": ["Preparatory"]})
    assert again.status_code == 409                                                   # no look-alike second account
    for typed in ("Sunita_RAO7", "sunita_rao7"):
        r = TestClient(app).post(f"{API}/auth/login", json={"identifier": typed, "password": "PassWord99"})
        assert r.status_code == 200 and r.json()["role"] == "TEACHER", (typed, r.text)
    wrong = TestClient(app).post(f"{API}/auth/login", json={"identifier": "Sunita_RAO7", "password": "password99"})
    assert wrong.status_code == 401                                                   # the password's case matters
    login_limits.reset()
