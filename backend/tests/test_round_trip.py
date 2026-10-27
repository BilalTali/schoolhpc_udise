"""Round trip on fake data, every stage: a filled card on (fake) PARAKH -> Fetch into the workbook -> the upload
check of that untouched workbook plans no change at all. Made-up students only."""
import pytest

from backend.hpc import sync
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups


@pytest.mark.parametrize("stage", ["Foundational", "Preparatory", "Middle"])
def test_an_untouched_workbook_plans_zero_differences(stage, tmp_path, monkeypatch):
    code = stage.upper()
    sids = ("1001", "1002")
    students = {}
    for sid in sids:
        data = blank_student(code, sid)
        students[(code, sid)] = {"record": data.record, "parts": data.raw_parts}
    portal = FakePortal(students)
    lookups = make_lookups(code, portal)
    monkeypatch.setattr(sync, "Lookups", lambda client, c: make_lookups(c, client))
    for sid in sids:                                            # the cards as a teacher finished them
        result = sync.sync_student(portal, stage, sid, filled_row(code), lookups, before_save=lambda d: None)
        assert result.status == "COMPLETED", result.errors
    saves = len(portal.saved)

    path, _ = sync.export_workbook(portal, [stage], tmp_path / "class.xlsx")
    grid = {k: v for k, v in filled_row(code).items() if k.startswith(("b_act_", "b_lvl_"))}   # the dashboard's Part B
    from backend.hpc import workbook
    rows = workbook.read(path)
    for sid in sids:                                            # Fetch marks completed cards Sync = No; check them anyway
        rows[sid][workbook.SYNC_KEY] = True
    monkeypatch.setattr(workbook, "read", lambda p, problems=None: rows)
    results = sync.sync_workbook(portal, path, dry_run=True, extra_values=lambda st, sid: grid)

    assert [(r.student_id, r.status, r.errors) for r in results] == [(sid, "READY", []) for sid in sids]
    assert {r.student_id: r.changes for r in results} == {sid: [] for sid in sids}
    assert len(portal.saved) == saves                           # the dry run wrote nothing
