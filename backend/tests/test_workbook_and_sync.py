"""Workbook round trip and the per-student sync against a fake portal."""
from backend.hpc import sync, workbook
from backend.hpc.portal import PortalError
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups


def _students():
    return [{"student_id": "1001", "student_name": "TEST STUDENT", "admission_number": "A1", "grade": "Grade 5",
             "section": "A", "status": "IN_PROGRESS"},
            {"student_id": "1002", "student_name": "DONE STUDENT", "admission_number": "A2", "grade": "Grade 5",
             "section": "A", "status": "COMPLETED"}]


def test_workbook_round_trip_with_several_stages(tmp_path):
    middle = [{"student_id": "2001", "student_name": "MIDDLE STUDENT", "status": "PENDING"}]
    sections = [workbook.Section("Preparatory", _students(), {"1001": filled_row("PREPARATORY")}, make_lookups("PREPARATORY")),
                workbook.Section("Middle", middle, {"2001": filled_row("MIDDLE")}, make_lookups("MIDDLE"))]
    path = workbook.build(sections, tmp_path / "class.xlsx")
    assert workbook.detect_stages(path) == ["Preparatory", "Middle"]
    rows = workbook.read(path)
    assert set(rows) == {"1001", "1002", "2001"}
    assert rows["1001"]["stage"] == "Preparatory" and rows["2001"]["stage"] == "Middle"
    assert rows["1001"]["sync"] is True and rows["1002"]["sync"] is False     # completed students default to No
    assert rows["1001"]["a1_mother_tongue"] == "Kashmiri" and rows["2001"]["b_strengths"] == "Collaboration"


def _portal_with_student():
    data = blank_student("PREPARATORY")
    return FakePortal({("PREPARATORY", "1001"): {"record": data.record, "parts": data.raw_parts}})


def test_sync_student_saves_parts_in_order_and_confirms_completion():
    portal = _portal_with_student()
    copies = []
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=copies.append)
    assert result.status == "COMPLETED", result.errors
    assert [p["hpc_col"] for _, _, p in portal.saved] == ["part_a1", "part_a2", "part_a3", "part_b", "part_c", "hpc_credit"]
    assert len(copies) == 1 and copies[0].student_id == "1001"      # copy taken before the first write


def test_no_save_without_a_snapshot():
    portal = _portal_with_student()
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal))
    assert result.status == "FAILED" and "no snapshot" in result.errors[0] and portal.saved == []

    def broken(data):
        raise OSError("disk full")
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=broken)
    assert result.status == "FAILED" and "disk full" in result.errors[0] and portal.saved == []


def test_invalid_student_is_not_written():
    portal = _portal_with_student()
    result = sync.sync_student(portal, "Preparatory", "1001", {}, make_lookups("PREPARATORY", portal))
    assert result.status == "INVALID" and result.errors and portal.saved == []


def test_dry_run_writes_nothing():
    portal = _portal_with_student()
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"),
                               make_lookups("PREPARATORY", portal), dry_run=True)
    assert result.status == "READY" and portal.saved == []


def test_portal_error_is_reported_as_failed():
    portal = _portal_with_student()

    def refuse(*args):
        raise PortalError("Portal session expired.")
    portal.save_part = refuse
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=lambda data: None)
    assert result.status == "FAILED" and "expired" in result.errors[0]


def test_snapshot_is_written_before_the_first_save_and_holds_parakh_values(tmp_path, monkeypatch):
    import json as _json
    from backend.services import snapshots
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snaps")
    portal = _portal_with_student()
    portal.students[("PREPARATORY", "1001")]["parts"]["part_a2"] = '{"gen": ["Asha", "9", ""]}'   # something on PARAKH
    saves_when_copied = []

    def take(data):
        saves_when_copied.append(len(portal.saved))
        return snapshots.take("teacher_test", "Preparatory", data, "test")
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=take)
    assert result.status == "COMPLETED" and saves_when_copied == [0]          # copied before anything was written
    [entry] = snapshots.list_for("teacher_test", "Preparatory", "1001")
    restored = snapshots.load("teacher_test", "Preparatory", "1001", entry["file"])
    assert _json.loads(restored.raw_parts["part_a2"])["gen"][:2] == ["Asha", "9"]   # the old value, not the new one
    assert restored.record["stu_info"]["student_name"] == "TEST STUDENT"



def test_a_successful_save_records_which_manual_activities_are_the_apps_own():
    from backend.hpc.stages import activity_grid
    portal = _portal_with_student()
    seen = []
    lk = make_lookups("PREPARATORY", portal)
    base = activity_grid.resolver_from_lookups(lk)

    def resolve(key):
        return base(key)
    resolve.remember = seen.append
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), lk,
                               resolve=resolve, before_save=lambda data: None)
    assert result.status == "COMPLETED" and len(seen) == 1
    saved_b = next(p for _, _, p in portal.saved if p["hpc_col"] == "part_b")
    assert seen[0] == saved_b["formdata"]
    # nothing is recorded when nothing is saved (a dry run)
    seen.clear()
    sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), lk, dry_run=True, resolve=resolve,
                      before_save=lambda data: None)
    assert seen == []


def test_each_step_of_a_save_is_reported_for_the_live_view():
    portal = _portal_with_student()
    steps = []
    result = sync.sync_student(portal, "Preparatory", "1001", filled_row("PREPARATORY"), make_lookups("PREPARATORY", portal),
                               before_save=lambda data: None, on_step=steps.append)
    assert result.status == "COMPLETED"
    assert steps[:3] == ["Reading the card from PARAKH", "Checking the values", "Keeping a copy of the card before saving"]
    assert steps[3:9] == [f"Saving {p} ({i} of 6)" for i, p in
                          enumerate(["Part A1", "Part A2", "Part A3", "Part B", "Part C", "HPC Credit"], start=1)]
    assert steps[-1] == "Checking that PARAKH shows the card completed"


def test_the_live_view_shows_the_current_step_and_a_short_history():
    from backend.services import upload_jobs
    upload_jobs._live.pop("job-x", None)
    upload_jobs._live_event("job-x", "1001", "STUDENT ONE", "Saving Part C (5 of 6)")
    view = upload_jobs.live_view("job-x")
    assert view["current"]["step"] == "Saving Part C (5 of 6)" and view["current"]["student_id"] == "1001"
    upload_jobs._live_event("job-x", "1001", "STUDENT ONE", "Saved to PARAKH", "saved")
    view = upload_jobs.live_view("job-x")
    assert view["current"] is None and [e["kind"] for e in view["events"]] == ["step", "saved"]
    for i in range(100):
        upload_jobs._live_event("job-x", "1002", "STUDENT TWO", f"step {i}")
    assert len(upload_jobs.live_view("job-x")["events"]) == upload_jobs.LIVE_EVENTS
    assert upload_jobs.live_view("unknown") == {"current": None, "events": []}
