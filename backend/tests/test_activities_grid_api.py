"""Activities grid endpoints, the workbook's read-only summary column and the upload path (fake PARAKH)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.hpc import sync, workbook
from backend.hpc.stages import get_stage
from backend.hpc.stages.activity import bank_dt
from backend.main import app
from backend.models.library import LibraryActivity, SchoolActivitySetting
from backend.routers import activities_grid as grid_router
from backend.routers import hpc_cards as cards_router
from backend.routers import teachers as teachers_router
from backend.services import activity_grid, hpc_cards, hpc_sessions, upload_jobs
from backend.tests.conftest import BANK_CONTENT, FakePortal, blank_student, filled_row, make_lookups

API = "/api/v1"
PREP = get_stage("PREPARATORY")
SUBJ = PREP.DOMAINS


def _activity(bank, domains, n=1, complete=True):
    dt = bank_dt(PREP.blank_activity, BANK_CONTENT, bank, True, lambda c: {}, ["proficient", "advance", "beginner"])
    dt.update({"domain": list(domains), "sa": [1] * 8})
    return {"nm": f"Bank {bank}", "id": f"x_{bank}_{n}", "is_complete": complete, "dt": dt}


@pytest.fixture
def grid_client(monkeypatch, tmp_path):
    client = TestClient(app)
    udise, username = "22222222222", "gridteacher"
    client.post(f"{API}/auth/school/register", json={
        "udise_code": udise, "school_name": "Grid School", "state": "JK", "district": "Budgam",
        "admin_name": "Admin", "admin_email": "grid@example.com", "password": "secret123"})
    admin = client.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"}).json()
    client.post(f"{API}/school/teachers", headers={"Authorization": f"Bearer {admin['access_token']}"}, json={
        "teacher_name": "Grid Teacher", "username": username, "password": "secret123", "assigned_stages": ["Preparatory"]})
    login = client.post(f"{API}/auth/login", json={"identifier": username, "password": "secret123"}).json()
    client.headers["Authorization"] = f"Bearer {login['access_token']}"

    students = {}
    for sid, part_b in (("1001", None), ("1002", [_activity(85, SUBJ)]),
                        ("1003", [_activity(85, SUBJ), _activity(85, ["PSLS4"], n=2)])):
        data = blank_student("PREPARATORY", sid)
        data.raw_parts["part_b"] = part_b
        students[("PREPARATORY", sid)] = {"record": data.record, "parts": data.raw_parts}
    portal = FakePortal(students)
    lookups = make_lookups("PREPARATORY", portal)
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    monkeypatch.setattr(teachers_router, "_portal", lambda teacher: portal)
    monkeypatch.setattr(grid_router, "_portal", lambda teacher: portal)
    monkeypatch.setattr(cards_router, "_portal", lambda teacher: portal)
    monkeypatch.setattr(sync, "Lookups", lambda p, code: lookups)          # workbook checks build their own
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, c, stage: lookups)
    roster = [{"student_id": sid, "student_name": f"STUDENT {sid}", "grade": "Grade 5", "section": "A",
               "status": "IN_PROGRESS"} for _, sid in students]
    (tmp_path / "roster_preparatory.json").write_text(json.dumps(roster), encoding="utf-8")
    with SessionLocal() as db:                      # no library: PARAKH's own lists are used
        db.query(LibraryActivity).delete()
        db.commit()
    activity_grid._cache.clear()
    return client, portal, tmp_path


def rows(client, **params):
    res = client.get(f"{API}/teacher/activities-grid/Preparatory", params=params)
    assert res.status_code == 200, res.text
    return res.json(), {r["student_id"]: r for r in res.json()["students"]}


def test_grid_shows_every_student_with_parakh_values_and_problems(grid_client):
    client, portal, _ = grid_client
    data, by_id = rows(client)
    assert [s["name"] for s in data["subjects"]][:2] == ["Language 1 (R1)", "Language 2 (R2)"]
    assert data["options"] == [{"key": "P85", "label": "85: Conversation in pairs"}]
    assert data["grades"] == ["Grade 5 - A"] and data["summary"] == {"ready": 2, "total": 3, "locked": 1}

    empty, done, locked = by_id["1001"], by_id["1002"], by_id["1003"]
    assert empty["ready"] is False and empty["problems"][0].startswith("No activity chosen for: Language 1 (R1)")
    assert done["ready"] is True and done["values"]["b_act_PSLS3"] == "P85"
    assert done["values"]["b_lvl_PSLS3_sensitivity"] == "Advanced" and done["source"]["b_act_PSLS3"] == "portal"
    assert locked["locked"] and locked["ready"] and "Kept exactly as it is" in locked["notes"][0]
    assert portal.saved == []                                     # reading the grid never writes


def test_autosave_with_versions_and_validation(grid_client):
    client, _, _ = grid_client
    url = f"{API}/teacher/activities-grid/Preparatory/1001"
    values = {f"b_act_{s}": "P85" for s in SUBJ}
    first = client.put(url, json={"values": values})
    assert first.status_code == 200, first.text
    row = first.json()
    assert row["draft_version"] == 1 and row["problems"][0].startswith("Levels not chosen for: Language 1 (R1)")

    levels = {f"b_lvl_{s}_{a}": "Proficient" for s in SUBJ for a in ("awareness", "sensitivity", "creativity")}
    assert client.put(url, json={"values": levels, "base_version": 0}).status_code == 409    # another window saved
    row = client.put(url, json={"values": levels, "base_version": 1}).json()
    assert row["ready"] and row["source"]["b_lvl_PSLS1_awareness"] == "draft"

    bad = client.put(url, json={"values": {"b_lvl_PSLS1_awareness": "Expert", "b_act_PSLS1": "P999", "zzz": "1"}})
    assert bad.status_code == 422
    problems = bad.json()["detail"]["problems"]
    assert set(problems) == {"b_lvl_PSLS1_awareness", "b_act_PSLS1", "zzz"} and "not offered" in problems["b_act_PSLS1"]
    assert client.put(f"{API}/teacher/activities-grid/Preparatory/9999", json={"values": {}}).status_code == 404


def test_quick_fill_whole_grade_preview_then_apply_keeps_filled_cells(grid_client):
    client, _, _ = grid_client
    url = f"{API}/teacher/activities-grid/Preparatory/quick-fill"
    body = {"activity_key": "P85", "grade": "Grade 5 - A",
            "levels": {"awareness": "Beginner", "sensitivity": "Beginner", "creativity": "Beginner"}}
    preview = client.post(url, json=body).json()
    # 1001: 7 activities + 21 levels. 1002 already has 85 and its own Awareness/Sensitivity levels (kept);
    # its Creativity is already Beginner. 1003 is locked.
    assert preview["applied"] is False and preview["cells"] == 28 and preview["students"] == 1
    assert preview["kept"] == 14 and [s["student_id"] for s in preview["skipped"]] == ["1003"]
    _, by_id = rows(client)
    assert by_id["1001"]["values"]["b_act_PSLS1"] == ""          # the preview changed nothing

    assert client.post(url, json={**body, "apply": True, "expected_cells": 5}).status_code == 409
    done = client.post(url, json={**body, "apply": True, "expected_cells": 28}).json()
    assert done["applied"] and done["cells"] == 28
    _, by_id = rows(client)
    assert by_id["1001"]["ready"] and by_id["1002"]["values"]["b_lvl_PSLS1_awareness"] == "Proficient"

    # one subject only, replacing what is there
    one = client.post(url, json={"activity_key": "", "subjects": ["PSLS3"], "students": ["1002"],
                                 "levels": {"creativity": "Advanced"}, "replace_filled": True, "apply": True}).json()
    assert one["cells"] == 1 and one["subjects"] == ["Mathematics"]
    _, by_id = rows(client)
    assert by_id["1002"]["values"]["b_lvl_PSLS3_creativity"] == "Advanced"
    assert "Update: Bank 85" in " ".join(by_id["1002"]["notes"]) or "Add" in " ".join(by_id["1002"]["notes"])
    assert client.post(url, json={"activity_key": "", "levels": {}}).status_code == 422


def test_locked_student_needs_replace_and_then_saves(grid_client):
    client, portal, _ = grid_client
    url = f"{API}/teacher/activities-grid/Preparatory/1003"
    row = client.put(url, json={"values": {"b_lvl_PSLS4_awareness": "Advanced"}}).json()
    assert not row["ready"] and "share subjects" in row["problems"][0]
    row = client.put(url, json={"values": {"b_replace": "Yes"}}).json()
    assert row["ready"], row["problems"]
    result = client.post(f"{API}/teacher/hpc-cards/Preparatory/1003/submit").json()
    assert result["status"] in ("INVALID", "COMPLETED")
    part_b_errors = [e for e in result["errors"] if e.startswith("Part B")]
    assert part_b_errors == []                                   # whatever else is missing, Part B is fine


def test_upload_sync_uses_the_grid_and_clears_it_afterwards(grid_client):
    client, portal, tmp_path = grid_client
    values = {**{f"b_act_{s}": "P85" for s in SUBJ},
              **{f"b_lvl_{s}_{a}": "Advanced" for s in SUBJ for a in ("awareness", "sensitivity", "creativity")}}
    client.put(f"{API}/teacher/activities-grid/Preparatory/1001", json={"values": values})

    lk = make_lookups("PREPARATORY", portal)
    row = {k: v for k, v in filled_row("PREPARATORY").items() if not k.startswith(("b_act_", "b_lvl_"))}
    section = workbook.Section("Preparatory", [{"student_id": "1001", "student_name": "STUDENT 1001", "status": "PENDING"}],
                               {"1001": row}, lk, activity_summaries={"1001": "Not chosen yet: everything"})
    path = workbook.build([section], tmp_path / "upload.xlsx")
    from backend.models.entities import Teacher
    with SessionLocal() as db:
        teacher_id = db.query(Teacher).filter_by(username="gridteacher").first().id

    report = upload_jobs.check_workbook(portal, path, teacher_id)
    assert report["is_valid"] and report["total_records"] == 1, report["errors"]
    results = sync.sync_workbook(portal, path, **upload_jobs._grid_hooks(portal, teacher_id),
                                 before_save_for=lambda stage: (lambda data: None))
    assert results[0].status == "COMPLETED", results[0].errors
    sent = next(p for _, sid, p in portal.saved if p["hpc_col"] == "part_b" and sid == "1001")
    assert sent["formdata"][0]["dt"]["awr"][3] == "advance" and sent["formdata"][0]["dt"]["domain"] == SUBJ

    activity_grid.clear_draft_values(teacher_id, portal.ay, "Preparatory", "1001")
    assert activity_grid.draft_values(teacher_id, portal.ay, "Preparatory", "1001") == {}


def test_workbook_summary_column_is_read_only_and_never_read(grid_client, tmp_path):
    client, portal, _ = grid_client
    lk = make_lookups("PREPARATORY", portal)
    section = workbook.Section("Preparatory", [{"student_id": "1002", "student_name": "S", "status": "PENDING"}],
                               {"1002": filled_row("PREPARATORY")}, lk,
                               activity_summaries={"1002": "Language 1 (R1): 85 (P/A/B)"})
    path = workbook.build([section], tmp_path / "w.xlsx")
    from openpyxl import load_workbook
    ws = load_workbook(path)["Prep B"]
    assert ws.cell(row=1, column=3).value == workbook.SUMMARY_HEADER and ws.cell(row=3, column=3).value.startswith("Language 1")
    assert ws.cell(row=2, column=3).value is None                # no key: the reader ignores it
    rule = next(dv for dv in ws.data_validations.dataValidation if "C3" in str(dv.sqref))
    assert rule.type == "custom" and rule.formula1 == "FALSE"
    headers = [c.value for c in ws[1]]
    assert "Activity (from Activity Bank)" not in headers and "Awareness level" not in headers
    assert len(headers) == 14                                    # Prep B: 14 columns (was 21)

    workbook.set_activity_summaries(path, {"Preparatory": {"1002": "updated text"}})
    assert load_workbook(path)["Prep B"].cell(row=3, column=3).value == "updated text"
    assert "Activities" not in json.dumps(workbook.read(path)["1002"])


def test_old_layout_workbook_imports_after_preview(grid_client):
    client, portal, tmp_path = grid_client
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "How to use"
    wb["How to use"]["A20"] = "Preparatory"
    ws = wb.create_sheet("B")
    for c, (label, key) in enumerate([("Student ID", "student_id"), ("Name", "student_name"), ("Activity", "b_activity"),
                                      ("Subjects", "b_subjects"), ("Aw", "b_awareness"), ("Se", "b_sensitivity"),
                                      ("Cr", "b_creativity")], start=1):
        ws.cell(row=1, column=c, value=label)
        ws.cell(row=2, column=c, value=key)
    for r, values in enumerate([["1001", "S1", "85: Conversation in pairs", "Language 1 (R1), Mathematics", "Advanced", "Beginner", "Proficient"],
                                ["1002", "S2", "", "", "", "", ""]], start=3):
        for c, v in enumerate(values, start=1):
            ws.cell(row=r, column=c, value=v)
    wb.save(tmp_path / "uploaded_old.xlsx")

    url = f"{API}/teacher/activities-grid/Preparatory/import-upload"
    preview = client.post(url, json={"file_name": "old.xlsx"}).json()
    assert preview["applied"] is False and preview["students"] == 1 and preview["cells"] == 8
    done = client.post(url, json={"file_name": "old.xlsx", "apply": True, "expected_cells": 8}).json()
    assert done["applied"] and list((tmp_path / "backups").iterdir())          # the original was backed up
    _, by_id = rows(client)
    v = by_id["1001"]["values"]
    assert v["b_act_PSLS1"] == "P85" and v["b_act_PSLS3"] == "P85" and v["b_act_PSLS2"] == ""
    assert v["b_lvl_PSLS3_awareness"] == "Advanced" and v["b_lvl_PSLS3_sensitivity"] == "Beginner"
    report = upload_jobs.check_workbook(portal, tmp_path / "uploaded_old.xlsx")
    assert any("old Activity columns" in w["message"] for w in report["warnings"])
