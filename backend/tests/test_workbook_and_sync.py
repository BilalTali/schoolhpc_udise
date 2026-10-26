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
