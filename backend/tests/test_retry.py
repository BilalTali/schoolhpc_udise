"""M-11: 'retry failed only' - a new job from the same uploaded file for the students whose save failed.
Made-up teacher, students and a fake PARAKH only."""
import uuid

import pytest
import requests
from fastapi.testclient import TestClient

from backend.hpc import sync, workbook
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups, session_headers

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}
IDS = ("1001", "1002", "1003")


@pytest.fixture
def world(monkeypatch, tmp_path):
    from backend.main import app
    from backend.routers import teachers
    from backend.services import hpc_sessions, upload_jobs
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    students = {}
    for sid in IDS:
        data = blank_student("PREPARATORY", sid)
        students[("PREPARATORY", sid)] = {"record": data.record, "parts": data.raw_parts}
    portal = FakePortal(students)
    portal.ay = "2627"
    broken = {"1001"}                                       # PARAKH drops the connection for this student, once
    real = portal.save_part

    def save(stage, sid, payload):
        if sid in broken and payload["hpc_col"] == "part_a2":
            broken.discard(sid)
            raise requests.ConnectionError("connection reset")
        return real(stage, sid, payload)
    portal.save_part = save
    monkeypatch.setattr(teachers, "_portal", lambda teacher: portal)
    monkeypatch.setattr(sync, "Lookups", lambda client, code: make_lookups(code, client))
    grid = {k: v for k, v in filled_row("PREPARATORY").items() if k.startswith(("b_act_", "b_lvl_"))}
    monkeypatch.setattr(upload_jobs, "_grid_hooks", lambda client, teacher_id: {"extra_values": lambda stage, sid: grid})

    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    admin = TestClient(app)
    admin.headers.update(HDR)
    admin.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Retry School", "state": "Test",
               "district": "Test", "admin_name": "Admin", "admin_email": f"rt.{tag}@example.com", "password": "secret123"})
    admin.headers.update(session_headers(udise)[0])
    tid = admin.post(f"{API}/school/teachers", json={"teacher_name": "Retry Teacher", "username": f"retry{tag}",
                     "password": "secret123", "assigned_stages": ["Preparatory"]}).json()["id"]
    client = TestClient(app)
    client.headers.update(session_headers(f"retry{tag}")[0])
    rows = {sid: filled_row("PREPARATORY") for sid in IDS}
    rows["1003"] = {**rows["1003"], "a1_mother_tongue": ""}                  # a mistake in the file: INVALID
    folder = hpc_sessions.session_dir("teacher", tid)
    workbook.build([workbook.Section("Preparatory", [{"student_id": s, "student_name": f"TEST STUDENT {s}", "status": "IN_PROGRESS"}
                                                     for s in IDS], rows, make_lookups("PREPARATORY"))], folder / "uploaded_class.xlsx")
    return {"client": client, "portal": portal, "folder": folder, "admin": admin, "tag": tag}


def _statuses(client, job_id):
    return {r["admission_number"]: r["status"] for r in client.get(f"{API}/teacher/upload/jobs/{job_id}/records").json()["records"]}


def test_retry_sends_only_the_students_whose_save_failed(world):
    c, portal = world["client"], world["portal"]
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    assert _statuses(c, first["job_id"]) == {"1001": "FAILED", "1002": "SUCCESS", "1003": "INVALID"}
    saves_before = len(portal.saved)

    retry = c.post(f"{API}/teacher/upload/jobs/{first['job_id']}/retry")
    assert retry.status_code == 200, retry.text
    second = retry.json()
    assert second["job_id"] != first["job_id"] and second["total_students"] == 1
    assert _statuses(c, second["job_id"]) == {"1001": "SUCCESS"}
    retried = {sid for _, sid, _ in portal.saved[saves_before:]}
    assert retried == {"1001"}                                     # 1002 (saved) and 1003 (file mistake) untouched
    assert c.post(f"{API}/teacher/upload/jobs/{second['job_id']}/retry").status_code == 409   # nothing failed now


def test_retry_refuses_when_the_file_was_replaced_since(world):
    c = world["client"]
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    (world["folder"] / "uploaded_class.xlsx").write_bytes(b"another file with the same name")
    r = c.post(f"{API}/teacher/upload/jobs/{first['job_id']}/retry")
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_only_the_teacher_who_owns_the_job_can_retry_it(world):
    c = world["client"]
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    world["admin"].post(f"{API}/school/teachers", json={"teacher_name": "Other", "username": f"other{world['tag']}",
                                                        "password": "secret123", "assigned_stages": ["Preparatory"]})
    other = TestClient(c.app)
    other.headers.update(session_headers(f"other{world['tag']}")[0])
    assert other.post(f"{API}/teacher/upload/jobs/{first['job_id']}/retry").status_code == 404
