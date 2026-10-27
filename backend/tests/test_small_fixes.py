"""Small low-risk fixes from the audit (L-2, L-5). Made-up schools and teachers only."""
import uuid

from fastapi.testclient import TestClient

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


def _school(client):
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    body = {"udise_code": udise, "school_name": f"Secret Name School {tag}", "state": "Test", "district": "Test",
            "admin_name": "Admin", "admin_email": f"a.{tag}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=body).status_code == 201
    return body, tag


def test_registering_a_taken_udise_does_not_show_the_other_schools_name():
    from backend.main import app
    client = TestClient(app)
    client.headers.update(HDR)
    body, tag = _school(client)
    again = client.post(f"{API}/auth/school/register", json={**body, "admin_email": f"other.{tag}@example.com"})
    assert again.status_code == 409 and body["school_name"] not in again.text
    same_email = client.post(f"{API}/auth/school/register", json={**body, "udise_code": "1" + body["udise_code"][1:]
                                                                  if body["udise_code"][0] != "1" else "2" + body["udise_code"][1:]})
    assert same_email.status_code == 409 and body["admin_email"] not in same_email.text


def test_a_teacher_without_grade_or_section_is_not_shown_an_invented_one():
    from backend.main import app
    client = TestClient(app)
    client.headers.update(HDR)
    body, tag = _school(client)
    client.post(f"{API}/auth/login", json={"identifier": body["udise_code"], "password": "secret123"})
    from backend.database import SessionLocal
    from backend.models.entities import Teacher
    made = client.post(f"{API}/school/teachers", json={"teacher_name": "Plain Teacher", "username": f"plain{tag}",
                                                       "password": "secret123", "assigned_stages": ["Middle"]}).json()
    with SessionLocal() as db:                                # an account made before grades were asked for
        t = db.get(Teacher, made["id"])
        t.assigned_grade, t.assigned_section = "", ""
        db.commit()
    listed = next(t for t in client.get(f"{API}/school/teachers").json() if t["id"] == made["id"])
    assert listed["assigned_grade"] in ("", None) and listed["assigned_grades"] == []
    assert listed["assigned_section"] in ("", None)


def test_a_teacher_works_only_in_their_own_stages(monkeypatch, tmp_path):
    """L-3: a stage the teacher is not assigned (in this app or on PARAKH) is refused."""
    from backend.main import app
    from backend.services import hpc_sessions
    from backend.tests.conftest import session_headers
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    client = TestClient(app)
    client.headers.update(HDR)
    body, tag = _school(client)
    client.headers.update(session_headers(body["udise_code"])[0])
    client.post(f"{API}/school/teachers", json={"teacher_name": "Middle Only", "username": f"midonly{tag}",
                                                "password": "secret123", "assigned_stages": ["Middle"]})
    t = TestClient(app)
    t.headers.update(session_headers(f"midonly{tag}")[0])
    assert t.get(f"{API}/teacher/settings/Middle").status_code == 200
    r = t.get(f"{API}/teacher/settings/Preparatory")
    assert r.status_code == 403 and "not one of your stages" in r.json()["detail"]


def test_two_library_syncs_started_together_make_one_job():
    """L-1: the 'already running?' check and the new job happen together."""
    import threading
    from backend.database import SessionLocal
    from backend.models.entities import School
    from backend.services import activity_library as lib
    tag = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        school = School(udise_code=str(int(tag, 16) % 10**11).zfill(11), school_name="Sync School", state="Test",
                        district="Test", admin_name="A", admin_email=f"sync.{tag}@example.com", hashed_password="x")
        db.add(school)
        db.commit()
        school_id = school.id
    actor = lib.Actor("SCHOOL_ADMIN", school_id, school_id, "Admin")
    barrier, results = threading.Barrier(4), []

    def start():
        barrier.wait()
        with SessionLocal() as db:
            job, already = lib.start_sync(db, actor, ["Preparatory"])
            results.append((job.id, already))
    threads = [threading.Thread(target=start) for _ in range(4)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert len({job_id for job_id, _ in results}) == 1 and sum(not already for _, already in results) == 1
