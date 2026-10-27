"""M-8: removing a teacher deactivates the account - the record of what was sent stays, the PARAKH session goes."""
import json
import uuid

from fastapi.testclient import TestClient

from backend.tests.conftest import session_headers

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


def test_removing_a_teacher_keeps_their_history_and_ends_their_access(monkeypatch, tmp_path):
    from backend.database import SessionLocal
    from backend.main import app
    from backend.models.entities import StudentRecord, Teacher, UploadJob
    from backend.services import hpc_sessions
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    admin = TestClient(app)
    admin.headers.update(HDR)
    admin.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Removal School", "state": "Test",
               "district": "Test", "admin_name": "Admin", "admin_email": f"r.{tag}@example.com", "password": "secret123"})
    admin.headers.update(session_headers(udise)[0])
    tid = admin.post(f"{API}/school/teachers", json={"teacher_name": "Leaving Teacher", "username": f"leaving{tag}",
                     "password": "secret123", "assigned_stages": ["Preparatory"]}).json()["id"]
    teacher_headers, _ = session_headers(f"leaving{tag}")
    folder = hpc_sessions.session_dir("teacher", tid)
    (folder / "session.json").write_text(json.dumps({"access_token": "made-up-parakh-token"}), encoding="utf-8")
    (folder / "roster_preparatory.json").write_text("[]", encoding="utf-8")
    with SessionLocal() as db:
        job = UploadJob(teacher_id=tid, original_filename="class.xlsx", detected_stage="Preparatory", status="COMPLETED")
        db.add(job)
        db.flush()
        db.add(StudentRecord(job_id=job.id, row_number=3, admission_number="1001", student_name="TEST STUDENT",
                             student_key="1001", status="SUCCESS"))
        db.commit()
        job_id = job.id

    assert admin.delete(f"{API}/school/teachers/{tid}").status_code == 204

    with SessionLocal() as db:
        t = db.get(Teacher, tid)
        assert t is not None and t.is_active is False                  # deactivated, not deleted
        assert db.get(UploadJob, job_id) is not None and len(db.get(UploadJob, job_id).records) == 1
    assert not (folder / "session.json").exists()                       # the PARAKH session is gone
    assert (folder / "roster_preparatory.json").exists()                # the rest is kept
    assert TestClient(app).get(f"{API}/auth/me", headers=teacher_headers).status_code == 401
    r = TestClient(app).post(f"{API}/auth/login", json={"identifier": f"leaving{tag}", "password": "secret123"})
    assert r.status_code == 403
    listed = next(t for t in admin.get(f"{API}/school/teachers").json() if t["id"] == tid)
    assert listed["is_active"] is False                                 # still listed, can be switched on again
    assert admin.put(f"{API}/school/teachers/{tid}", json={"is_active": True}).status_code == 200
    assert TestClient(app).post(f"{API}/auth/login", json={"identifier": f"leaving{tag}", "password": "secret123"}).status_code == 200
