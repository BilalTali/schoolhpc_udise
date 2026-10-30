"""H-2: no route blocks the server. Routes are plain functions (FastAPI runs them in worker threads); a route
written as `async def` runs on the server's one event loop, so any slow work in it stops every other request."""
import asyncio
import importlib
import threading
import time
import uuid

from fastapi.testclient import TestClient

from backend.hpc import workbook
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}
ASYNC_ALLOWED = set()          # async routes that are known to do no blocking work


def test_no_route_is_async_unless_known_to_be_safe():
    found = set()
    for m in ("auth", "schools", "teachers", "hpc_cards", "activity_library", "activities_grid", "class_template", "platform"):
        for r in importlib.import_module(f"backend.routers.{m}").router.routes:
            if asyncio.iscoroutinefunction(r.endpoint):
                found.add(f"{m}.{r.endpoint.__name__}")
    assert found <= ASYNC_ALLOWED, f"async routes that could block the server: {sorted(found - ASYNC_ALLOWED)}"


def test_other_requests_are_answered_while_an_upload_is_checked(monkeypatch, tmp_path):
    from backend.main import app
    from backend.routers import teachers
    from backend.services import hpc_sessions, upload_jobs
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    stu = blank_student("PREPARATORY")
    monkeypatch.setattr(teachers, "_portal", lambda teacher: FakePortal({("PREPARATORY", "1001"): {"record": stu.record,
                                                                                                    "parts": stu.raw_parts}}))

    def slow_check(client, path, teacher_id=None, full=True):   # like PARAKH answering slowly
        time.sleep(2)
        return {"is_valid": True, "total_records": 1, "detected_stage": "Preparatory", "error_count": 0, "warning_count": 0,
                "errors": [], "warnings": [], "seeder_working_days": "", "seeder_max_marks": "", "ready_students": []}
    monkeypatch.setattr(upload_jobs, "check_workbook", slow_check)
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    path = tmp_path / "class.xlsx"
    workbook.build([workbook.Section("Preparatory", [{"student_id": "1001", "student_name": "TEST STUDENT", "status": "IN_PROGRESS"}],
                                     {"1001": filled_row("PREPARATORY")}, make_lookups("PREPARATORY"))], path)
    with TestClient(app) as client:                             # one server loop for every request, like uvicorn
        client.headers.update(HDR)
        client.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Loop School", "state": "Test",
                    "district": "Test", "admin_name": "Loop Admin", "admin_email": f"l.{tag}@example.com", "password": "secret123"})
        client.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"})
        client.post(f"{API}/school/teachers", json={"teacher_name": "Loop Teacher", "username": f"loop{tag}",
                    "password": "secret123", "assigned_stages": ["Preparatory"]})
        client.post(f"{API}/auth/login", json={"identifier": f"loop{tag}", "password": "secret123"})
        done = {}

        def validate():
            done["status"] = client.post(f"{API}/teacher/upload/validate",
                                         files={"file": ("class.xlsx", path.read_bytes())}).status_code
        t = threading.Thread(target=validate)
        t.start()
        time.sleep(0.5)                                         # the check is running now
        start = time.time()
        assert client.get("/").status_code == 200
        waited = time.time() - start
        t.join()
    assert done["status"] == 200
    assert waited < 1.0, f"a simple request waited {waited:.1f} s while the upload was checked"
