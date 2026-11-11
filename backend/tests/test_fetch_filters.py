"""A teacher's fetch reads only their own remaining students: their School Register classes, not COMPLETED."""
from backend.hpc import sync
from backend.tests.conftest import FakePortal, blank_student, make_lookups


def _portal(monkeypatch, statuses, sections):
    students = {}
    for sid in statuses:
        data = blank_student("PREPARATORY", sid)
        data.record["stu_info"]["section_id"] = sections[sid]
        students[("PREPARATORY", sid)] = {"record": data.record, "parts": data.raw_parts}
    portal = FakePortal(students)
    real = portal.roster
    portal.roster = lambda stage: [{**r, "hpc_status": statuses[r["id"]]} for r in real(stage)]
    monkeypatch.setattr(sync, "Lookups", lambda client, c: make_lookups(c, client))
    return portal


def test_completed_students_and_other_classes_are_not_fetched(monkeypatch, tmp_path):
    statuses = {"1": "PENDING", "2": "COMPLETED", "3": "IN_PROGRESS", "4": "PENDING"}
    portal = _portal(monkeypatch, statuses, {"1": 1, "2": 1, "3": 1, "4": 2})
    grade = blank_student("PREPARATORY", "1").record["stu_info"]["grade_id"]
    _, by_stage = sync.export_workbook(portal, ["Preparatory"], tmp_path / "w.xlsx", skip_completed=True,
                                       classes={(grade, 1)})
    assert [s["student_id"] for s in by_stage["Preparatory"]] == ["1", "3"]
    assert portal.completed_skipped["Preparatory"] == 1 and portal.other_classes_skipped["Preparatory"] == 1


def test_without_the_options_everyone_is_fetched(monkeypatch, tmp_path):
    portal = _portal(monkeypatch, {"1": "COMPLETED", "2": "PENDING"}, {"1": 1, "2": 2})
    _, by_stage = sync.export_workbook(portal, ["Preparatory"], tmp_path / "w.xlsx")
    assert len(by_stage["Preparatory"]) == 2
