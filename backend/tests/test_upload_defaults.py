"""The Excel upload's cell check uses what the save uses: the mother tongue default and the School Register."""
from backend.hpc import workbook
from backend.services import hpc_cards, upload_jobs
from backend.tests.conftest import make_lookups


def _errors(monkeypatch, school):
    monkeypatch.setattr(workbook, "layout", lambda path: ({}, {}))
    monkeypatch.setattr(workbook, "detect_stages", lambda path: ["Preparatory"])
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, c, stage: make_lookups("PREPARATORY"))
    monkeypatch.setattr(upload_jobs, "_school_values_for", lambda client, tid: (lambda stage, sid: school))
    rows = {"1001": {workbook.STAGE_KEY: "Preparatory", workbook.SYNC_KEY: "Yes", workbook.NAME_KEY: "A",
                     "a1_mother_tongue": "", "a1_guardian_relation": "Father", "a1_guardian_name": "", "d_1_obtained": ""}}
    found = upload_jobs.file_cell_errors(None, "t1", None, rows, {})
    return {e["column"].split(" (column")[0] for e in found}


def test_empty_mother_tongue_is_not_an_error_it_is_saved_as_kashmiri(monkeypatch):
    assert not any("Mother Tongue" in c for c in _errors(monkeypatch, {}))


def test_parent_and_marks_from_the_school_register_are_not_reported_empty(monkeypatch):
    without = _errors(monkeypatch, {})
    assert any("Guardian Name" in c for c in without)                       # really empty: reported
    given = _errors(monkeypatch, {"a1_guardian_name": "Abdul Rashid", "d_1_obtained": 40})
    assert not any("Guardian Name" in c for c in given) and not any("marks obtained" in c and "R1" in c for c in given)
