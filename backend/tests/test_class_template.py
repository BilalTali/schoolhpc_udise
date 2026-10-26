"""Class settings, the Part-B-complete check and the class template (fake PARAKH, synthetic students only)."""
import copy
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.database import SessionLocal
from backend.hpc import sync, template, workbook
from backend.hpc.stages import get_stage
from backend.hpc.stages.activity import bank_dt
from backend.main import app
from backend.models.entities import Teacher
from backend.models.library import LibraryActivity
from backend.models.settings import ClassSetting
from backend.routers import class_template as ct_router
from backend.routers import teachers as teachers_router
from backend.services import class_settings, class_template, hpc_cards, hpc_sessions, upload_jobs
from backend.tests.conftest import BANK_CONTENT, FakePortal, blank_student, filled_row, make_lookups

API = "/api/v1"
PREP = get_stage("PREPARATORY")
SUBJ = PREP.DOMAINS
SETTINGS = {"medium": "English", "rural_urban": "Rural", "working_days": [22] * 12,
            "max_marks": {str(n): 50 for n in range(1, 7)}, "declaration": "Yes"}


def grid(levels="Proficient", skip=()):
    out = {}
    for s in SUBJ:
        if s in skip:
            continue
        out[f"b_act_{s}"] = "P85"
        out.update({f"b_lvl_{s}_{a}": levels for a in ("awareness", "sensitivity", "creativity")})
    return out


ANSWERS = {f"b_self_{i}": "Yes" for i in range(1, 9)}


@pytest.fixture
def world(monkeypatch, tmp_path):
    client = TestClient(app)
    client.post(f"{API}/auth/school/register", json={
        "udise_code": "55555555555", "school_name": "Template School", "state": "JK", "district": "Budgam",
        "admin_name": "Admin", "admin_email": "tpl@example.com", "password": "secret123"})
    admin = client.post(f"{API}/auth/login", json={"identifier": "55555555555", "password": "secret123"}).json()
    client.post(f"{API}/school/teachers", headers={"Authorization": f"Bearer {admin['access_token']}"}, json={
        "teacher_name": "Template Teacher", "username": "tplteacher", "password": "secret123", "assigned_stages": ["Preparatory"]})
    login = client.post(f"{API}/auth/login", json={"identifier": "tplteacher", "password": "secret123"}).json()
    client.headers["Authorization"] = f"Bearer {login['access_token']}"
    with SessionLocal() as db:
        t = db.query(Teacher).filter_by(username="tplteacher").first()
        teacher = SimpleNamespace(id=t.id, school_id=t.school_id)
        db.query(LibraryActivity).delete()
        db.query(ClassSetting).filter_by(teacher_id=t.id).delete()
        db.commit()

    students = {}
    for sid in ("3001", "3002", "3003", "3004"):
        data = blank_student("PREPARATORY", sid)
        students[("PREPARATORY", sid)] = {"record": data.record, "parts": data.raw_parts}
    # 3004 already has two activities on PARAKH (no overlap): 85 for R1..TW, 91 for the rest, both finished
    acts = []
    for n, (bank, subs) in enumerate(((85, SUBJ[:4]), (91, SUBJ[4:])), start=1):
        dt = bank_dt(PREP.blank_activity, BANK_CONTENT, bank, True, lambda c: {}, ["proficient"] * 3)
        dt.update({"domain": list(subs), "sa": [1] * 8})
        acts.append({"nm": f"Bank {bank}", "id": f"3004_{bank}_{n}", "is_complete": True, "dt": dt})
    students[("PREPARATORY", "3004")]["parts"]["part_b"] = acts
    portal = FakePortal(students)
    lookups = make_lookups("PREPARATORY", portal)
    lookups.activities[91] = {**copy.deepcopy(lookups.activities[85]), "id": 91, "activity_caption": "Bank 91"}
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    for mod in (teachers_router, ct_router):
        monkeypatch.setattr(mod, "_portal", lambda t: portal)
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, c, stage: lookups)
    monkeypatch.setattr(sync, "Lookups", lambda p, code: lookups)
    roster = [{"student_id": sid, "student_name": f"PUPIL {sid}", "grade": "Grade 5", "section": "A", "status": "PENDING"}
              for _, sid in students]
    (tmp_path / "roster_preparatory.json").write_text(json.dumps(roster), encoding="utf-8")
    class_template._jobs.clear()
    return client, portal, lookups, teacher, tmp_path


def run_check(client):
    started = client.post(f"{API}/teacher/template/Preparatory/check")
    assert started.status_code == 200, started.text
    for _ in range(100):
        job = client.get(f"{API}/teacher/template/Preparatory/check").json()["job"]
        if job["status"] != "RUNNING":
            return job
        time.sleep(0.05)
    raise AssertionError("check did not finish")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_validation_completeness_and_versions(world):
    client, *_ = world
    url = f"{API}/teacher/settings/Preparatory"
    first = client.get(url).json()
    assert first["complete"] is False and "Medium of instruction" in first["missing"]
    assert first["choices"]["medium"] == ["English", "Hindi"] and len(first["marks_subjects"]) == 6

    bad = client.put(url, json={"values": {**SETTINGS, "medium": "Klingon", "working_days": [22, 40] + [22] * 10}})
    assert bad.status_code == 422
    problems = bad.json()["detail"]["problems"]
    assert "medium" in problems and problems["working_days.1"] == "May: between 0 and 31."

    saved = client.put(url, json={"values": {**SETTINGS, "working_days": [0] + [22] * 11}, "version": 0}).json()
    assert saved["complete"] is True and saved["version"] == 1
    assert saved["warnings"]["working_days.0"].startswith("April: 0 working days is unusual")
    assert client.put(url, json={"values": SETTINGS, "version": 0}).status_code == 409          # stale window
    assert class_settings.row_values("Preparatory", SETTINGS)["d_3_max"] == 50


# ---------------------------------------------------------------------------
# Readiness: the real save's Part B checks
# ---------------------------------------------------------------------------

def test_mixed_class_ready_and_not_ready_with_reasons(world):
    client, portal, lookups, teacher, _ = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid(), **ANSWERS})         # ready
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3002", {**grid(skip=("PSLS3",)), **ANSWERS})  # no Maths
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3003", grid())                        # answers missing
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3004", ANSWERS)                       # two activities kept
    job = run_check(client)
    by = {s["student_id"]: s for s in job["students"]}
    assert job["status"] == "COMPLETED" and job["total"] == 4 and job["ready"] == 2
    assert by["3001"]["ready"] and by["3004"]["ready"]
    assert by["3002"]["part_b_problems"] == ["No activity chosen for: Mathematics"] and by["3002"]["fix"] == "activities"
    assert not by["3003"]["ready"] and by["3003"]["fix"] == "card"
    assert any("Self-assessment" in p for p in by["3003"]["part_b_problems"])
    assert portal.saved == []                                                     # reading only


def test_zero_ready_and_all_ready(world):
    client, portal, lookups, teacher, _ = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    job = run_check(client)
    assert job["ready"] == 1                                    # only 3004 (its activities are on PARAKH already)
    assert client.get(f"{API}/teacher/template/Preparatory/download").status_code == 200
    for sid in ("3001", "3002", "3003"):
        hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", sid, {**grid(), **ANSWERS})
    assert run_check(client)["ready"] == 4

    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3004", {"b_replace": "Yes", **grid(skip=tuple(SUBJ))})
    for sid in ("3001", "3002", "3003"):
        hpc_cards.delete_draft(teacher.id, portal.ay, "Preparatory", sid)
    portal.students[("PREPARATORY", "3004")]["parts"]["part_b"] = None
    hpc_cards.delete_draft(teacher.id, portal.ay, "Preparatory", "3004")
    assert run_check(client)["ready"] == 0
    zero = client.get(f"{API}/teacher/template/Preparatory/download")
    assert zero.status_code == 409 and "No student's Part B is complete" in zero.json()["detail"]


def test_download_needs_settings_first_and_all_needs_confirmation(world):
    client, portal, lookups, teacher, _ = world
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid(), **ANSWERS})
    run_check(client)
    blocked = client.get(f"{API}/teacher/template/Preparatory/download")
    assert blocked.status_code == 409 and "Finish the class settings first" in blocked.json()["detail"]
    status = client.get(f"{API}/teacher/template/Preparatory/check").json()
    assert status["settings_complete"] is False and status["settings_missing"]
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    run_check(client)
    assert client.get(f"{API}/teacher/template/Preparatory/download", params={"include": "all"}).status_code == 409
    assert client.get(f"{API}/teacher/template/Preparatory/download",
                      params={"include": "all", "confirmed": True}).status_code == 200


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

def test_template_layout_only_ready_students_locked_sheets_ids_only(world):
    client, portal, lookups, teacher, tmp_path = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid("Advanced"), **ANSWERS,
                                                                        "a1_mother_tongue": "Kashmiri"})   # from bulk entry
    run_check(client)
    res = client.get(f"{API}/teacher/template/Preparatory/download")
    path = tmp_path / "dl.xlsx"
    path.write_bytes(res.content)
    wb = load_workbook(path)
    assert wb.sheetnames[:2] == ["How to use", "Preparatory"]
    assert {"Exceptions", "Part B (from dashboard)", "Settings", "Class summary"} <= set(wb.sheetnames)

    ws = wb["Preparatory"]
    keys = [c.value for c in ws[3]]
    ids = [ws.cell(row=r, column=1).value for r in range(4, ws.max_row + 1)]
    assert sorted(ids) == ["3001", "3004"]                                    # only Part-B-complete students
    assert "a1_working_1" not in keys and "a1_medium" not in keys and "d_1_max" not in keys and "d_declaration" not in keys
    assert "d_1_obtained" in keys and "a1_present_1" in keys and "c_PSLS1_awareness" in keys
    assert not any(str(k or "").startswith("b_") for k in keys)                 # nothing of Part B to type
    assert ws.protection.sheet is True and ws["E4"].protection.locked is False and ws["A4"].protection.locked is True
    assert ws.row_dimensions[3].hidden and ws.freeze_panes == "E4"
    r3001 = next(r for r in range(4, ws.max_row + 1) if ws.cell(row=r, column=1).value == "3001")
    mt = keys.index("a1_mother_tongue") + 1
    assert ws.cell(row=r3001, column=mt).value == "Kashmiri" and ws.cell(row=r3001, column=mt).protection.locked is False
    assert any(dv.type == "decimal" for dv in ws.data_validations.dataValidation)            # marks capped at max

    b = wb["Part B (from dashboard)"]
    row = [c.value for c in b[3]]
    assert row[0] in ("3001", "3004") and b.protection.sheet is True
    first = next(r for r in b.iter_rows(min_row=3, values_only=True) if r[0] == "3001")
    assert "85: Conversation in pairs" in first[2] and first[3] == "A/A/A"
    s = wb["Settings"]
    assert s["B4"].value == "English" and s.protection.sheet is True

    summary = wb["Class summary"]
    text = json.dumps([[c.value for c in r] for r in summary.iter_rows()], default=str)
    assert "PUPIL" not in text and "3002" in text and "No activity chosen" in text           # IDs and reasons, no names
    info = template.info(wb)
    assert sorted(info["included"]) == ["3001", "3004"] and info["ready_as_of"]


def test_exceptions_are_read_back_and_bad_rows_reported(world):
    client, portal, lookups, teacher, tmp_path = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid(), **ANSWERS})
    run_check(client)
    path = tmp_path / "dl.xlsx"
    path.write_bytes(client.get(f"{API}/teacher/template/Preparatory/download").content)
    wb = load_workbook(path)
    ex = wb["Exceptions"]
    for r, values in enumerate([("3001", "Working days - April", 20), ("3001", "Medium of Instruction", "Hindi"),
                                ("9999", "Working days - May", 10), ("3001", "Shoe size", 5)], start=2):
        for c, v in enumerate(values, start=1):
            ex.cell(row=r, column=c, value=v)
    wb.save(path)
    problems = []
    rows = workbook.read(path, problems)
    assert rows["3001"]["a1_working_1"] == 20 and rows["3001"]["a1_medium"] == "Hindi"
    assert "a1_working_2" not in rows["3001"]                                  # settings come from the dashboard
    assert len(problems) == 2 and "9999" in problems[0] and "Shoe size" in problems[1]


def test_upload_rechecks_and_skips_a_student_who_became_unready(world):
    client, portal, lookups, teacher, tmp_path = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    for sid in ("3001", "3002"):
        hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", sid, {**grid(), **ANSWERS})
    run_check(client)
    path = tmp_path / "dl.xlsx"
    path.write_bytes(client.get(f"{API}/teacher/template/Preparatory/download").content)
    wb = load_workbook(path)
    ws = wb["Preparatory"]
    keys = [c.value for c in ws[3]]
    fill = {k: v for k, v in filled_row("PREPARATORY").items() if k in keys and not k.startswith("b_")}
    for r in range(4, ws.max_row + 1):
        for k, v in fill.items():
            ws.cell(row=r, column=keys.index(k) + 1, value=v)
    wb["Exceptions"]["A2"], wb["Exceptions"]["B2"], wb["Exceptions"]["C2"] = "3001", "Working days - April", 20
    wb.save(path)

    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3002", {"b_act_PSLS5": ""})   # Art taken off after download
    report = upload_jobs.check_workbook(portal, path, teacher.id)
    assert report["total_records"] == 2                                      # 3001 and 3004 ready, 3002 skipped
    [skipped] = report["errors"]
    assert skipped["field"].endswith("Part B - Activity")
    assert skipped["message"].startswith("no longer ready since the file was made") and "Art Education" in skipped["message"]
    changes = [w for w in report["warnings"] if w["severity"] == "INFO" and "3001" in w["field"]]
    message = changes[0]["message"]
    assert message.startswith("Will change on PARAKH: A1 (") and "Part B activities" in message
    assert "Mother Tongue" in message and "Kashmiri" not in message           # field names only, never values
    assert upload_jobs.change_summary(["A1: Working days - Apr"]) == "A1 (1 field). First: Working days - Apr"
    assert portal.saved == []                                               # the check never writes
