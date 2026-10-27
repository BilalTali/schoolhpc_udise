"""H-1: a network error or an unexpected error fails one student, never the whole upload, and the result
says which parts reached PARAKH before it stopped. Made-up students and a fake PARAKH only."""
import uuid

import pytest
import requests

from backend.hpc import portal as portal_mod, sync, workbook
from backend.hpc.portal import PortalError
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups


def test_a_network_error_reaches_the_app_as_a_portal_error(monkeypatch):
    session = portal_mod.Session(access_token="t", staff={"staff_id": f"net-{uuid.uuid4().hex}"})
    client = portal_mod.Portal(session)
    client.min_interval = 0

    def down(*args, **kwargs):
        raise requests.ConnectionError("connection reset by peer")
    monkeypatch.setattr(client.http, "request", down)
    with pytest.raises(PortalError, match="PARAKH did not answer"):
        client.student("Preparatory", "1001")
    monkeypatch.setattr(client.http, "request", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("read timed out")))
    with pytest.raises(PortalError, match="PARAKH did not answer"):
        client.student("Preparatory", "1001")


def _two_students():
    out = {}
    for sid in ("1001", "1002"):
        data = blank_student("PREPARATORY", sid)
        out[("PREPARATORY", sid)] = {"record": data.record, "parts": data.raw_parts}
    return FakePortal(out)


def _breaks_on(portal, student_id, part, error):
    real = portal.save_part

    def save(stage, sid, payload):
        if sid == student_id and payload["hpc_col"] == part:
            raise error
        return real(stage, sid, payload)
    portal.save_part = save


@pytest.mark.parametrize("error", [requests.ConnectionError("connection reset"), PortalError("PARAKH did not answer"),
                                   RuntimeError("something unexpected")])
def test_a_student_that_fails_midway_says_which_parts_were_saved(error):
    portal = _two_students()
    _breaks_on(portal, "1001", "part_a3", error)
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=lambda data: None)
    assert result.status == "FAILED"
    assert result.saved_parts == ["part_a1", "part_a2"] and result.failed_part == "part_a3"
    assert result.errors[0].startswith("Part A1, Part A2 saved; Part A3 failed")


def test_an_unexpected_error_before_saving_fails_only_that_student():
    portal = _two_students()
    portal.student = lambda *a, **k: (_ for _ in ()).throw(ValueError("bad answer from PARAKH"))
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=lambda data: None)
    assert result.status == "FAILED" and result.saved_parts == [] and "bad answer" in result.errors[0]


def test_an_upload_job_goes_on_after_one_student_fails(tmp_path, monkeypatch):
    """The upload runner end to end: one student breaks midway, the next is still saved."""
    from backend.database import SessionLocal, init_db
    from backend.models.entities import School, StudentRecord, Teacher, UploadJob
    from backend.services import upload_jobs
    portal = _two_students()
    _breaks_on(portal, "1001", "part_a3", requests.ConnectionError("connection reset"))
    monkeypatch.setattr(sync, "Lookups", lambda client, code: make_lookups(code, client))
    grid = {k: v for k, v in filled_row("PREPARATORY").items() if k.startswith("b_act_") or k.startswith("b_lvl_")}
    monkeypatch.setattr(upload_jobs, "_grid_hooks", lambda client, teacher_id: {"extra_values": lambda stage, sid: grid})
    students = [{"student_id": sid, "student_name": f"TEST STUDENT {sid}", "status": "IN_PROGRESS"} for sid in ("1001", "1002")]
    rows = {sid: filled_row("PREPARATORY") for sid in ("1001", "1002")}
    path = workbook.build([workbook.Section("Preparatory", students, rows, make_lookups("PREPARATORY"))], tmp_path / "class.xlsx")

    init_db()                                  # the tables, when this file runs on its own
    tag = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        school = School(udise_code=str(int(tag, 16) % 10**11).zfill(11), school_name="Job School", state="T", district="T",
                        admin_name="A", admin_email=f"job.{tag}@example.com", hashed_password="x")
        db.add(school)
        db.flush()
        teacher = Teacher(school_id=school.id, teacher_name="Job Teacher", username=f"job{tag}", hashed_password="x")
        db.add(teacher)
        db.flush()
        job = UploadJob(teacher_id=teacher.id, original_filename="class.xlsx", detected_stage="Preparatory", status="PENDING",
                        total_students=2)
        db.add(job)
        db.flush()
        for n, sid in enumerate(("1001", "1002"), start=3):
            db.add(StudentRecord(job_id=job.id, row_number=n, admission_number=sid, student_name=f"TEST STUDENT {sid}",
                                 student_key=sid, status="PENDING"))
        db.commit()
        job_id = job.id

    upload_jobs.run_job(job_id, portal, str(path))

    with SessionLocal() as db:
        job = db.get(UploadJob, job_id)
        recs = {r.admission_number: r for r in job.records}
        assert job.status == "PARTIAL_SUCCESS" and job.success_count == 1 and job.failed_count == 1
        assert recs["1002"].status == "SUCCESS"
        assert recs["1001"].status == "FAILED"
        assert recs["1001"].error_message.startswith("Part A1, Part A2 saved; Part A3 failed")
        assert recs["1001"].verification_result == "Saved: part_a1, part_a2; failed at: part_a3"
    saved = [(sid, p["hpc_col"]) for _, sid, p in portal.saved]
    assert ("1001", "part_a3") not in saved and [c for s, c in saved if s == "1002"][-1] == "hpc_credit"


def test_a_slow_read_is_asked_again_but_a_save_is_sent_once(monkeypatch):
    session = portal_mod.Session(access_token="t", staff={"staff_id": f"slow-{uuid.uuid4().hex}"})
    client = portal_mod.Portal(session)
    client.min_interval, client.RETRY_WAIT = 0, 0
    calls = []

    class Ok:
        status_code, ok, text = 200, True, ""
        def json(self):
            return {"success": True, "data": {"formdata": None}}

    def flaky(method, url, **kwargs):
        calls.append(method)
        if len(calls) < 3:
            raise requests.ReadTimeout("read timed out")
        return Ok()
    monkeypatch.setattr(client.http, "request", flaky)
    assert client.student("Preparatory", "1001") == {"formdata": None} and calls == ["GET", "GET", "GET"]
    calls.clear()
    monkeypatch.setattr(client.http, "request", lambda m, u, **k: (calls.append(m), (_ for _ in ()).throw(requests.ReadTimeout("x")))[1])
    with pytest.raises(PortalError):
        client.save_part("Preparatory", "1001", {"hpc_col": "part_a1"})
    assert calls == ["PATCH"]                                       # never sent twice
