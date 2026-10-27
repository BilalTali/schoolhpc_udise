"""H-5: text is written as text cells and a leading '=' is never read as a formula. Made-up values only."""
import pytest
from openpyxl import load_workbook

from backend.hpc import sync, template, workbook
from backend.hpc.credit import summative_subjects
from backend.services import class_settings
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

TRICKY = {"a1_mother_tongue": "=Kashmiri", "a1_guardian_name": "+91 Raju", "a1_other_interest": "-dash", "a1_udid": "@home",
          "a1_low_attendance": "=CMD|' /C calc'!A0"}
NAMES = ["=HYPERLINK(\"http://x\")", "+PLUS NAME", "-MINUS NAME", "@AT NAME"]
IDS = ["1001", "1002", "1003", "1004"]


def _template(tmp_path):
    settings = {"medium": "English", "rural_urban": "Rural", "working_days": [22] * 12,
                "max_marks": {n: 50 for n, _ in summative_subjects("Preparatory")}, "declaration": "Yes"}
    sec = {"stage": "Preparatory", "students": [{"student_id": i, "student_name": n} for i, n in zip(IDS, NAMES)],
           "rows": {i: {**filled_row("PREPARATORY"), **TRICKY} for i in IDS}, "lookups": make_lookups("PREPARATORY"),
           "settings": settings, "marks_subjects": summative_subjects("Preparatory"),
           "is_setting_key": class_settings.is_setting_key, "part_b": {}, "problems": {}}
    summary = {"generated_at": "x", "ready_as_of": "x", "classes": "", "included_count": 4, "excluded_count": 0, "rule": "t",
               "settings_saved_at": "-", "students": [{"student_id": i, "in_file": True, "ready": True, "part_b_problems": [],
                                                       "other_problems": [], "stage": "Preparatory"} for i in IDS]}
    path = tmp_path / "template.xlsx"
    template.build_many(path, [sec], summary)
    return path


def _formula_cells(path):
    wb = load_workbook(path)
    return {(ws.title, c.coordinate): c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.data_type == "f"}


def test_the_template_writes_names_and_answers_as_text(tmp_path):
    formulas = _formula_cells(_template(tmp_path))
    assert formulas, "the template's own formulas (attendance %, settings totals) are still formulas"
    assert all(v.startswith(("=IF(", "=SUM(")) for v in formulas.values()), formulas
    texts = {c.value for ws in load_workbook(tmp_path / "template.xlsx").worksheets for row in ws.iter_rows() for c in row
             if c.data_type == "s"}
    assert set(NAMES) <= texts and set(TRICKY.values()) <= texts


def test_text_starting_with_equals_plus_minus_or_at_comes_back_unchanged(tmp_path):
    rows = workbook.read(_template(tmp_path))
    for sid in IDS:
        assert {k: rows[sid][k] for k in TRICKY} == TRICKY
        assert rows[sid][workbook.NAME_KEY] in NAMES


def test_the_old_class_workbook_writes_text_too(tmp_path):
    students = [{"student_id": i, "student_name": n, "status": "IN_PROGRESS"} for i, n in zip(IDS, NAMES)]
    path = workbook.build([workbook.Section("Preparatory", students, {i: {**filled_row("PREPARATORY"), **TRICKY} for i in IDS},
                                            make_lookups("PREPARATORY"))], tmp_path / "class.xlsx")
    assert _formula_cells(path) == {}
    rows = workbook.read(path)
    assert all({k: rows[sid][k] for k in TRICKY} == TRICKY for sid in IDS)


@pytest.mark.parametrize("sheet_kind", ["students", "exceptions"])
def test_a_formula_typed_into_an_answer_is_refused_not_calculated(tmp_path, sheet_kind, monkeypatch):
    path = _template(tmp_path)
    wb = load_workbook(path)
    if sheet_kind == "students":
        ws = wb["Preparatory"]
        keys = {ws.cell(row=3, column=c).value: c for c in range(1, ws.max_column + 1)}
        ws.cell(row=4, column=keys["a1_mother_tongue"], value="=C5")          # what Excel stores when a teacher types =C5
        where = ws.cell(row=4, column=keys["a1_mother_tongue"]).coordinate
    else:
        ws = wb[template.sheet_names("Preparatory", combined=False)["exceptions"]]
        ws["A2"], ws["B2"], ws["C2"] = "1001", "Working days - April", "=10+8"
        where = "C2"
    wb.save(path)
    rows = workbook.read(path)
    assert any("formula" in p and where in p for p in rows["1001"][workbook.PROBLEMS_KEY])
    data = {("PREPARATORY", sid): {"record": blank_student("PREPARATORY", sid).record,
                                   "parts": blank_student("PREPARATORY", sid).raw_parts} for sid in IDS}
    monkeypatch.setattr(sync, "Lookups", lambda client, code: make_lookups(code, client))
    results = {r.student_id: r for r in sync.sync_workbook(FakePortal(data), path, dry_run=True)}
    assert results["1001"].status == "INVALID" and any("formula" in e and where in e for e in results["1001"].errors)


# H-6: the same student twice is never merged - both rows are skipped and the upload says why
def test_a_student_twice_on_one_sheet_is_skipped_not_merged(tmp_path, monkeypatch):
    path = _template(tmp_path)
    wb = load_workbook(path)
    ws = wb["Preparatory"]
    keys = {ws.cell(row=3, column=c).value: c for c in range(1, ws.max_column + 1)}
    ws.cell(row=5, column=keys["student_id"], value="1001")          # a copied row kept the first student's id
    ws.cell(row=5, column=keys["a1_mother_tongue"], value=None)
    wb.save(path)
    rows = workbook.read(path)
    assert rows["1001"]["a1_mother_tongue"] == "=Kashmiri"            # the first row's value, not merged with blanks
    assert any("rows 4 and 5" in p and "Preparatory" in p for p in rows["1001"][workbook.PROBLEMS_KEY])
    data = {("PREPARATORY", sid): {"record": blank_student("PREPARATORY", sid).record,
                                   "parts": blank_student("PREPARATORY", sid).raw_parts} for sid in IDS}
    monkeypatch.setattr(sync, "Lookups", lambda client, code: make_lookups(code, client))
    results = {r.student_id: r for r in sync.sync_workbook(FakePortal(data), path, dry_run=True)}
    assert results["1001"].status == "INVALID" and "appears twice" in results["1001"].errors[0]


def test_a_student_on_two_stage_sheets_is_skipped(tmp_path):
    def section(stage, ids):
        settings = {"medium": "English", "rural_urban": "Rural", "working_days": [22] * 12,
                    "max_marks": {n: 50 for n, _ in summative_subjects(stage)}, "declaration": "Yes"}
        return {"stage": stage, "students": [{"student_id": i, "student_name": f"STUDENT {i}"} for i in ids],
                "rows": {i: {} for i in ids}, "lookups": make_lookups(stage.upper()), "settings": settings,
                "marks_subjects": summative_subjects(stage), "is_setting_key": class_settings.is_setting_key,
                "part_b": {}, "problems": {}}
    summary = {"generated_at": "x", "ready_as_of": "x", "classes": "", "included_count": 2, "excluded_count": 0, "rule": "t",
               "settings_saved_at": "-", "students": []}
    path = tmp_path / "all.xlsx"
    template.build_many(path, [section("Preparatory", ["5001"]), section("Middle", ["5001"])], summary)
    rows = workbook.read(path)
    assert any("Preparatory" in p and "Middle" in p for p in rows["5001"][workbook.PROBLEMS_KEY])


def test_the_old_class_workbook_still_joins_a_student_across_its_part_sheets(tmp_path):
    students = [{"student_id": "1001", "student_name": "TEST STUDENT", "status": "IN_PROGRESS"}]
    path = workbook.build([workbook.Section("Preparatory", students, {"1001": filled_row("PREPARATORY")},
                                            make_lookups("PREPARATORY"))], tmp_path / "class.xlsx")
    rows = workbook.read(path)
    assert not rows["1001"].get(workbook.PROBLEMS_KEY) and rows["1001"]["a1_mother_tongue"] == "Kashmiri"


# M-13: text answers use Excel's Text format, so what a teacher types (e.g. 007) is kept as typed;
# numbers (attendance, marks) keep the normal format so they still add up and the live checks still compare them
def _formats(ws, key_row):
    keys = {ws.cell(row=key_row, column=c).value: c for c in range(1, ws.max_column + 1)}
    return {k: ws.cell(row=key_row + 1, column=c).number_format for k, c in keys.items() if k}


def test_text_answers_are_text_cells_and_numbers_stay_numbers(tmp_path):
    fmt = _formats(load_workbook(_template(tmp_path))["Preparatory"], 3)
    for key in ("a1_mother_tongue", "a1_guardian_name", "a1_udid", "a2_name", "a2_age", "c_PSLS1_remark"):
        if key in fmt:
            assert fmt[key] == "@", (key, fmt[key])
    for key in ("a1_working_1", "a1_present_1", "d_1_max", "d_1_obtained", "a1_medium", "sync"):
        if key in fmt:
            assert fmt[key] != "@", (key, fmt[key])


def test_the_old_class_workbook_uses_text_cells_for_text_too(tmp_path):
    students = [{"student_id": "1001", "student_name": "TEST STUDENT", "status": "IN_PROGRESS"}]
    path = workbook.build([workbook.Section("Preparatory", students, {"1001": filled_row("PREPARATORY")},
                                            make_lookups("PREPARATORY"))], tmp_path / "class.xlsx")
    wb = load_workbook(path)
    seen = {}
    for ws in wb.worksheets:
        if ws.max_row >= 3 and workbook.ID_KEY in [c.value for c in ws[2]]:
            seen.update(_formats(ws, 2))
    assert seen["a1_mother_tongue"] == "@" and seen["a1_working_1"] != "@"
