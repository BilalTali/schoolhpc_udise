"""API smoke test: register a school, add a teacher, log in as that teacher (temporary SQLite DB)."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
API = "/api/v1"


def test_school_and_teacher_flow():
    school = {"udise_code": "01234567890", "school_name": "Test School", "state": "JK", "district": "Budgam",
              "admin_name": "Admin", "admin_email": "admin@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=school).status_code == 201
    assert client.post(f"{API}/auth/school/register", json=school).status_code == 409      # one school = one registration

    admin = client.post(f"{API}/auth/login", json={"identifier": "01234567890", "password": "secret123"}).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    teacher = {"teacher_name": "Test Teacher", "username": "tteacher", "password": "secret123",
               "assigned_stages": ["Preparatory", "Middle"]}
    created = client.post(f"{API}/school/teachers", json=teacher, headers=headers)
    assert created.status_code == 201 and created.json()["assigned_stages"] == ["Preparatory", "Middle"]
    assert client.get(f"{API}/school/stats", headers=headers).json()["total_teachers"] == 1

    login = client.post(f"{API}/auth/login", json={"identifier": "tteacher", "password": "secret123"}).json()
    t_headers = {"Authorization": f"Bearer {login['access_token']}"}
    status = client.get(f"{API}/teacher/hpc/status", headers=t_headers).json()
    assert status["logged_in"] is False and status["has_credentials"] is False
    # Without a portal session the roster cannot be fetched, and the API says why.
    roster = client.post(f"{API}/teacher/roster/sync?stage=Preparatory", headers=t_headers)
    assert roster.status_code == 401 and "Start HPC Session" in roster.json()["detail"]
    assert client.get(f"{API}/teacher/upload/jobs", headers=t_headers).json() == []
