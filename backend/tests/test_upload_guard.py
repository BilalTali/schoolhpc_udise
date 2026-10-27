"""H-3: one active upload per teacher - a lock in the app and a unique rule in the database.
Made-up teacher, students and a fake PARAKH only."""
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.hpc import workbook
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


@pytest.fixture
def uploader(monkeypatch, tmp_path):
    from backend.main import app
    from backend.routers import teachers
    from backend.services import hpc_sessions, upload_jobs
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    stu = blank_student("PREPARATORY")
    portal = FakePortal({("PREPARATORY", "1001"): {"record": stu.record, "parts": stu.raw_parts}})
    monkeypatch.setattr(teachers, "_portal", lambda teacher: portal)
    runs = []

    def slow_run(job_id, client, path, teacher_id=None):     # a job that stays active for a moment
        runs.append(job_id)
        time.sleep(0.5)
    monkeypatch.setattr(upload_jobs, "run_job", slow_run)

    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    admin = TestClient(app)
    admin.headers.update(HDR)
    reg = admin.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Guard School", "state": "Test",
               "district": "Test", "admin_name": "Guard Admin", "admin_email": f"g.{tag}@example.com", "password": "secret123"})
    assert reg.status_code == 201, reg.text
    login = admin.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"})
    assert login.status_code == 200, login.text
    tid = admin.post(f"{API}/school/teachers", json={"teacher_name": "Guard Teacher", "username": f"guard{tag}",
                     "password": "secret123", "assigned_stages": ["Preparatory"]})
    assert tid.status_code == 201, tid.text
    tid = tid.json()["id"]
    client = TestClient(app)
    client.headers.update(HDR)
    client.post(f"{API}/auth/login", json={"identifier": f"guard{tag}", "password": "secret123"})
    folder = hpc_sessions.session_dir("teacher", tid)
    students = [{"student_id": "1001", "student_name": "TEST STUDENT", "status": "IN_PROGRESS"}]
    workbook.build([workbook.Section("Preparatory", students, {"1001": filled_row("PREPARATORY")},
                                     make_lookups("PREPARATORY"))], folder / "uploaded_class.xlsx")
    return {"client": client, "teacher_id": tid, "runs": runs}


def test_two_submits_at_the_same_moment_start_one_job(uploader):
    client, answers = uploader["client"], []
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait()
        answers.append(client.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).status_code)
    threads = [threading.Thread(target=submit) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(answers) == [200, 409] and len(uploader["runs"]) == 1


def test_the_database_refuses_a_second_active_job_for_the_same_teacher(uploader):
    from backend.database import SessionLocal
    from backend.models.entities import UploadJob
    tid = uploader["teacher_id"]
    with SessionLocal() as db:
        db.add(UploadJob(teacher_id=tid, original_filename="a.xlsx", detected_stage="Preparatory", status="PENDING",
                         active_teacher_id=tid))
        db.commit()
        db.add(UploadJob(teacher_id=tid, original_filename="b.xlsx", detected_stage="Preparatory", status="PENDING",
                         active_teacher_id=tid))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.query(UploadJob).filter(UploadJob.teacher_id == tid).delete()
        db.commit()


def test_a_finished_or_interrupted_job_frees_the_teacher(uploader, monkeypatch, tmp_path):
    from backend.database import SessionLocal
    from backend.models.entities import UploadJob
    from backend.services import upload_jobs
    tid = uploader["teacher_id"]
    with SessionLocal() as db:
        job = UploadJob(teacher_id=tid, original_filename="a.xlsx", detected_stage="Preparatory", status="IN_PROGRESS",
                        active_teacher_id=tid)
        db.add(job)
        db.commit()
        job_id = job.id
    upload_jobs.recover_interrupted_jobs()                      # a restart in the middle of a job
    with SessionLocal() as db:
        job = db.get(UploadJob, job_id)
        assert job.status == "FAILED" and job.active_teacher_id is None
    r = uploader["client"].post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"})
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(UploadJob, r.json()["job_id"]).active_teacher_id == tid      # held while it runs


def test_init_db_adds_the_unique_rule_to_an_older_database(tmp_path):
    """Databases made before the guard get the column and its unique index at startup."""
    from sqlalchemy import create_engine, inspect, text
    from backend import database
    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE upload_jobs (id VARCHAR(36) PRIMARY KEY, teacher_id VARCHAR(36) NOT NULL, "
                          "original_filename VARCHAR(255) NOT NULL, detected_stage VARCHAR(30) NOT NULL)"))
    database.migrate(engine)
    insp = inspect(engine)
    assert "active_teacher_id" in {c["name"] for c in insp.get_columns("upload_jobs")}
    assert any(i["unique"] and i["column_names"] == ["active_teacher_id"] for i in insp.get_indexes("upload_jobs"))
