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


def test_the_saved_and_the_not_saved_students_come_back_as_two_excel_files(world):
    import io
    from openpyxl import load_workbook
    from backend.services.upload_jobs import RESULT_SHEET
    c = world["client"]
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    (world["folder"] / "uploaded_class.xlsx").write_bytes(b"the next upload with the same name")   # the job kept its own copy

    def sheets(which):
        r = c.get(f"{API}/teacher/upload/jobs/{first['job_id']}/workbook", params={"which": which})
        assert r.status_code == 200, r.text
        wb = load_workbook(io.BytesIO(r.content))
        result = [row for row in wb[RESULT_SHEET].iter_rows(min_row=2, values_only=True)]
        return wb, result

    wb, result = sheets("not_saved")
    assert wb.sheetnames[0] == RESULT_SHEET
    assert {row[0] for row in result} == {"1001", "1003"}                 # PARAKH failure and the file mistake
    assert all(row[3] for row in result)                                  # each with its reason
    path = world["folder"] / "not_saved.xlsx"
    wb.save(path)
    rows = workbook.read(path)                                            # uploading it again syncs just those two
    assert {sid for sid, row in rows.items() if row[workbook.SYNC_KEY]} == {"1001", "1003"}

    _, result = sheets("saved")
    assert [row[0] for row in result] == ["1002"]
    assert c.get(f"{API}/teacher/upload/jobs/{first['job_id']}/workbook", params={"which": "all"}).status_code == 422


def test_sync_sends_only_the_students_the_check_found_complete(world, monkeypatch):
    c, portal, folder = world["client"], world["portal"], world["folder"]
    data = (folder / "uploaded_class.xlsx").read_bytes()
    from backend.services import upload_jobs
    monkeypatch.setattr(upload_jobs, "file_cell_errors", lambda client, tid, path, rows, hooks: [
        {"row": 5, "field": "TEST STUDENT 1003 (ID 1003)", "student_id": "1003", "severity": "ERROR", "sheet": "Students",
         "column": "Mother Tongue (column D)", "message": "required", "rejected_value": None, "guidance": ""}])
    report = c.post(f"{API}/teacher/upload/validate", files={"file": ("class.xlsx", data)}).json()
    assert report["is_valid"] and report["total_records"] == 2
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    statuses = _statuses(c, first["job_id"])
    assert statuses["1003"] == "INVALID" and statuses["1002"] == "SUCCESS"
    records = c.get(f"{API}/teacher/upload/jobs/{first['job_id']}/records").json()["records"]
    [held] = [r for r in records if r["admission_number"] == "1003"]
    assert held["error_message"].startswith("Not sent - fix in the file: Mother Tongue (column D): required")
    assert held["attempt_count"] == 0                                     # never sent to PARAKH
    assert "1003" not in {sid for _, sid, _ in portal.saved}

    (folder / "uploaded_class.xlsx").write_bytes(data + b" ")             # changed after the check: check again
    assert c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).status_code == 409


def test_a_saved_student_with_the_same_answers_is_not_sent_again(world, monkeypatch):
    c, folder = world["client"], world["folder"]
    from backend.services import activity_grid, upload_jobs
    monkeypatch.setattr(upload_jobs, "file_cell_errors", lambda client, tid, path, rows, hooks: [])
    grid = {k: v for k, v in filled_row("PREPARATORY").items() if k.startswith(("b_act_", "b_lvl_"))}
    cleared = set()                                                       # like the real grid: cleared once saved
    monkeypatch.setattr(upload_jobs, "_grid_hooks", lambda client, teacher_id: {
        "extra_values": lambda stage, sid: {} if sid in cleared else grid})
    monkeypatch.setattr(activity_grid, "forget", lambda *a: None)
    monkeypatch.setattr(activity_grid, "clear_draft_values", lambda tid, ay, stage, sid: cleared.add(sid))
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    assert _statuses(c, first["job_id"])["1002"] == "SUCCESS"
    data = (folder / "uploaded_class.xlsx").read_bytes()

    report = c.post(f"{API}/teacher/upload/validate", files={"file": ("class.xlsx", data)}).json()
    assert report["already_saved"] >= 1                                   # 1002: saved, nothing changed since
    assert any("1002" in w["field"] and "Already saved" in w["message"] for w in report["warnings"])
    assert c.get(f"{API}/teacher/upload/checked").json()["report"]["file_name"] == "class.xlsx"   # kept for a reload

    second = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    assert "1002" not in _statuses(c, second["job_id"])                   # not sent again
    assert c.get(f"{API}/teacher/upload/checked").json()["report"]["file_name"] == "class.xlsx"   # still no re-check
    third = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()   # Sync again, same check
    assert "1002" not in _statuses(c, third["job_id"])                    # whoever was saved since is left out


def test_parakh_lists_timing_out_do_not_stop_the_whole_upload(world, monkeypatch):
    from backend.hpc.portal import PortalError
    c = world["client"]
    monkeypatch.setattr(sync, "LOOKUP_WAIT", 0)
    calls = {"n": 0}

    def slow_then_fine(client, code):                                    # PARAKH times out twice, then answers
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PortalError("PARAKH did not answer (ReadTimeout)")
        return make_lookups(code, client)
    monkeypatch.setattr(sync, "Lookups", slow_then_fine)
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    assert _statuses(c, first["job_id"])["1002"] == "SUCCESS"            # asked again, then saved

    asked = {"n": 0}

    def never(client, code):
        asked["n"] += 1
        raise PortalError("PARAKH did not answer (ReadTimeout)")
    monkeypatch.setattr(sync, "Lookups", never)
    second = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    job = c.get(f"{API}/teacher/upload/jobs/{second['job_id']}/records").json()
    assert job["status"] == "FAILED"
    assert all(r["status"] == "FAILED" and "lists for Preparatory did not load" in r["error_message"]
               for r in job["records"] if r["status"] != "INVALID")         # each one, retry later; nothing written
    assert asked["n"] <= 2 * sync.LOOKUP_TRIES                            # once per round, not once per student


def test_a_save_parakh_did_not_answer_is_checked_then_sent_again(world, monkeypatch):
    from backend.hpc.portal import PortalError
    c, portal = world["client"], world["portal"]
    monkeypatch.setattr(sync, "SAVE_RECHECK_WAIT", 0)
    real = portal.save_part
    stalls = {("1002", "part_a1"): "lost", ("1002", "part_c"): "kept"}    # no answer: once not saved, once saved

    def save(stage, sid, payload):
        how = stalls.pop((sid, payload["hpc_col"]), None)
        if how == "kept":
            real(stage, sid, payload)                                     # PARAKH saved it, then went quiet
        if how:
            raise PortalError("PARAKH did not answer (ReadTimeout). Please try again in a few minutes.")
        return real(stage, sid, payload)
    portal.save_part = save
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    assert _statuses(c, first["job_id"])["1002"] == "SUCCESS"
    cols = [col for _, sid, col in [(s, i, p["hpc_col"]) for s, i, p in portal.saved] if sid == "1002"] \
        if portal.saved and isinstance(portal.saved[0][2], dict) else None
    assert not stalls


def test_students_parakh_did_not_answer_for_get_a_second_round(world, monkeypatch):
    from backend.hpc.portal import PortalError
    from backend.services import upload_jobs
    c, portal = world["client"], world["portal"]
    monkeypatch.setattr(upload_jobs, "SECOND_ROUND_WAIT", 0)
    real = portal.student
    quiet = {"1002"}                                                      # PARAKH stalls on this card, once

    def student(stage, sid, hpc_col=None):
        if sid in quiet:
            quiet.discard(sid)
            raise PortalError("PARAKH did not answer (ReadTimeout). Please try again in a few minutes.")
        return real(stage, sid, hpc_col)
    portal.student = student
    first = c.post(f"{API}/teacher/upload/submit", params={"file_name": "class.xlsx"}).json()
    records = {r["admission_number"]: r for r in c.get(f"{API}/teacher/upload/jobs/{first['job_id']}/records").json()["records"]}
    assert records["1002"]["status"] == "SUCCESS" and records["1002"]["attempt_count"] == 2
    assert records["1003"]["status"] == "INVALID" and records["1003"]["attempt_count"] == 1   # a file mistake: once


def test_a_part_read_back_as_a_json_string_counts_as_the_same():
    assert sync._same('{"b": [1, 2], "a": "x"}', {"a": "x", "b": [1, 2]})
    assert sync._same('{"a":1}', '{ "a": 1 }')
    assert not sync._same('{"a": 1}', {"a": 2})
