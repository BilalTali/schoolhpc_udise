"""Class settings, the Part-B-complete check and the class template (fake PARAKH, synthetic students only)."""
import copy
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

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
from backend.tests.conftest import BANK_CONTENT, FakePortal, blank_student, filled_row, make_lookups, session_headers

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
    admin_headers, _ = session_headers("55555555555")
    client.post(f"{API}/school/teachers", headers=admin_headers, json={
        "teacher_name": "Template Teacher", "username": "tplteacher", "password": "secret123", "assigned_stages": ["Preparatory"]})
    client.headers.update(session_headers("tplteacher")[0])
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
    assert blocked.status_code == 409 and "Finish the class settings" in blocked.json()["detail"]
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
    assert ws.protection.sheet is True and ws["D4"].protection.locked is False and ws["A4"].protection.locked is True
    assert ws.row_dimensions[3].hidden and ws.freeze_panes == "D4"
    assert ws["D2"].value != "To fill or check (when the file was made)" and keys[3]          # no problems column
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


def test_problems_are_live_cell_colours(world):
    """Red where a value is wrong, yellow where a required one is empty; Excel works them out as the teacher types."""
    client, portal, lookups, teacher, tmp_path = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid(), **ANSWERS})
    run_check(client)
    path = tmp_path / "dl.xlsx"
    path.write_bytes(client.get(f"{API}/teacher/template/Preparatory/download").content)
    ws = load_workbook(path)["Preparatory"]
    keys = [c.value for c in ws[3]]
    rules = {}
    for area, items in ws.conditional_formatting._cf_rules.items():
        rules[str(area.sqref)] = [(r.formula[0], r.dxf.fill.fgColor.rgb if r.dxf and r.dxf.fill else None) for r in items]
    col = lambda key: get_column_letter(keys.index(key) + 1)

    may = rules[f"{col('a1_present_2')}4:{col('a1_present_2')}5"]
    red = [f for f, colour in may if colour and colour.endswith("FECACA")]
    assert len(red) == 1 and f"{col('a1_present_2')}4>IF(COUNTIFS('Exceptions'!$A:$A,$A4,'Exceptions'!$B:$B,\"Working days - May\")>0" in red[0]
    assert red[0].endswith("'Settings'!$B$7))")                       # May's class working days, unless an exception
    marks = rules[f"{col('d_1_obtained')}4:{col('d_1_obtained')}5"]
    assert any(colour and colour.endswith("FEF3C7") and f == f'AND($C4<>"No",LEN(TRIM({col("d_1_obtained")}4))=0)'
               for f, colour in marks)                                 # yellow while empty (not for Sync = No)
    assert any('"Max marks - ' in f and "'Settings'!$B$" in f for f, _ in marks)
    level = rules[f"{col('c_PSLS1_awareness')}4:{col('c_PSLS1_awareness')}5"]
    assert any("COUNTIF(Lists!" in f for f, _ in level)               # a value not in the list is red


def test_a_blank_mark_is_reported_once():
    from backend.hpc import sync
    from backend.tests.conftest import blank_student, filled_row, make_lookups
    row = {**filled_row("PREPARATORY"), "d_3_obtained": ""}
    _, errors = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), row, make_lookups("PREPARATORY"))
    maths = [e for e in errors if "Mathematics" in e and e.startswith("HPC Credit")]
    assert len(maths) == 1 and maths[0].endswith("summative marks obtained: required")


def test_short_forms_are_read_as_the_full_answer():
    from backend.hpc.fields import Field
    yes_no = Field("x", "Declaration", ("d",), "choice", {"Yes": True, "No": False})
    four = Field("y", "How I feel", ("f",), "choice", {"Yes": "1", "Sometimes": "2", "No": "3", "Not sure": "4"})
    level = Field("z", "Maths: Awareness", ("c",), "choice", {"Beginner": "beginner", "Proficient": "proficient", "Advanced": "advance"})
    assert yes_no.parse("n") == (False, None) and yes_no.parse("Y") == (True, None)
    assert four.parse("no") == ("3", None) and four.parse("not") == ("4", None) and four.parse("SOME") == ("2", None)
    assert four.parse("n")[1] == "How I feel: 'n' could be No or Not sure - type a few more letters"
    assert level.parse("prof") == ("proficient", None) and level.parse("adv") == ("advance", None)
    assert level.parse("Excellent")[1].startswith("Maths: Awareness: 'Excellent' is not one of")


def test_excel_functions_stay_usable_and_long_text_wraps(world):
    client, portal, lookups, teacher, tmp_path = world
    client.put(f"{API}/teacher/settings/Preparatory", json={"values": SETTINGS})
    hpc_cards.save_draft(teacher.id, portal.ay, "Preparatory", "3001", {**grid(), **ANSWERS})
    run_check(client)
    path = tmp_path / "dl.xlsx"
    path.write_bytes(client.get(f"{API}/teacher/template/Preparatory/download").content)
    ws = load_workbook(path)["Preparatory"]
    assert ws.protection.sheet and not ws.protection.formatCells and not ws.protection.formatRows
    keys = [c.value for c in ws[3]]
    remark = ws.cell(row=4, column=keys.index("c_PSLS1_remark") + 1)
    assert remark.alignment.wrap_text and ws.row_dimensions[4].height is None      # the row grows to fit
    level = get_column_letter(keys.index("c_PSLS1_awareness") + 1)
    rules = [r.formula[0] for area, items in ws.conditional_formatting._cf_rules.items()
             if str(area.sqref).startswith(level + "4") for r in items]
    assert any('&"*")<>1' in f for f in rules)                                    # a short form is not red


def test_one_file_for_several_stages_reads_back_by_stage(tmp_path):
    """A sheet per stage, each with its own Settings, Exceptions and Part B; the upload knows each row's stage."""
    from backend.hpc import workbook
    from backend.hpc.credit import summative_subjects
    from backend.tests.conftest import make_lookups

    def section(stage, code, ids):
        settings = {"medium": "English", "rural_urban": "Rural", "working_days": [22] * 12,
                    "max_marks": {n: 50 for n, _ in summative_subjects(stage)}, "declaration": "Yes"}
        return {"stage": stage, "students": [{"student_id": i, "student_name": f"STUDENT {i}"} for i in ids],
                "rows": {i: {} for i in ids}, "lookups": make_lookups(code), "settings": settings,
                "marks_subjects": summative_subjects(stage), "is_setting_key": class_settings.is_setting_key,
                "part_b": {}, "problems": {}}
    summary = {"generated_at": "2026-10-27T09:00:00+00:00", "ready_as_of": "2026-10-27T08:55:00+00:00", "classes": "Grade 5 A, Grade 6 A",
               "included_count": 3, "excluded_count": 0, "rule": "test", "settings_saved_at": "-",
               "students": [{"student_id": i, "in_file": True, "ready": True, "part_b_problems": [], "other_problems": [], "stage": st}
                            for i, st in (("5001", "Preparatory"), ("5002", "Preparatory"), ("6001", "Middle"))]}
    path = tmp_path / "all.xlsx"
    template.build_many(path, [section("Preparatory", "PREPARATORY", ["5001", "5002"]), section("Middle", "MIDDLE", ["6001"])], summary)

    wb = load_workbook(path)
    assert wb.sheetnames[:3] == ["How to use", "Preparatory", "Middle"]                     # sheet 1, sheet 2 ...
    for st in ("Preparatory", "Middle"):
        assert {f"{st} - Settings", f"{st} - Exceptions", f"{st} - Part B"} <= set(wb.sheetnames)
    assert "Settings" not in wb.sheetnames and wb["How to use"]["A20"].value == "Preparatory, Middle"
    rules = [r.formula[0] for items in wb["Middle"].conditional_formatting._cf_rules.values() for r in items]
    assert any("'Middle - Settings'!$B$" in f for f in rules) and any("'Middle - Exceptions'!" in f for f in rules)
    assert not any("'Preparatory - " in f for f in rules)                                    # each sheet uses its own stage
    wb["Middle - Exceptions"]["A2"], wb["Middle - Exceptions"]["B2"], wb["Middle - Exceptions"]["C2"] = "6001", "Working days - April", 18
    wb["Preparatory - Exceptions"]["A2"], wb["Preparatory - Exceptions"]["B2"], wb["Preparatory - Exceptions"]["C2"] = "6001", "Working days - May", 9
    wb.save(path)

    problems = []
    rows = workbook.read(path, problems)
    assert {sid: r["stage"] for sid, r in rows.items()} == {"5001": "Preparatory", "5002": "Preparatory", "6001": "Middle"}
    assert rows["6001"]["a1_working_1"] == 18 and "a1_working_2" not in rows["6001"]       # Middle's exception only
    assert any("6001" in p and "not in this file" in p for p in problems)                   # wrong stage's sheet: reported
    assert sorted(workbook.detect_stages(path)) == ["Middle", "Preparatory"]
    info = template.info(load_workbook(path))
    assert info["stages"] == ["Preparatory", "Middle"] and sorted(info["included"]) == ["5001", "5002", "6001"]
