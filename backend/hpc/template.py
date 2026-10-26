"""
The class template: what the teacher fills in Excel once the dashboard has done the rest.

Sheets
  How to use                 instructions (A20 = the stage, as in every workbook from this app)
  <Stage>                    one row per student (only students whose Part B is complete, unless the teacher
                             chose "all"): Sync, a Problems column, then parts A1, A2 (A3, A4), C and the marks
                             obtained, each part a coloured band and a collapsible column group. Row 1 = part,
                             row 2 = column header, row 3 = field key (hidden; how the file is read back).
                             Only the cells a teacher fills are unlocked; the sheet is protected.
  Exceptions                 one row per per-student exception to the class settings (Student ID, what, value)
  Part B (from dashboard)    locked: each subject's activity and levels, and the Part B answers
  Settings                   locked: the class settings as used
  Class summary              locked: when it was made, "ready as of", who is in the file and who is not and why (IDs)
  Lists                      hidden: dropdown values
Settings, Part B and the summary are never read back: an upload always takes them from the dashboard.
"""
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from backend.hpc.stages import activity_grid, get_stage

ID_KEY, NAME_KEY, SYNC_KEY = "student_id", "student_name", "sync"
SUMMARY_SHEET, SETTINGS_SHEET, PART_B_SHEET, EXCEPTIONS_SHEET = "Class summary", "Settings", "Part B (from dashboard)", "Exceptions"
LOCKED_SHEETS = ("How to use", "Lists", SUMMARY_SHEET, SETTINGS_SHEET, PART_B_SHEET, EXCEPTIONS_SHEET)
FIRST_DATA_ROW = 4
BAND_COLOURS = ["1F4E78", "375623", "7F6000", "833C0B", "3A3838", "203864", "4D0F28"]
WHITE_BOLD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
REQUIRED_FILL = PatternFill("solid", fgColor="F8CBAD")
LOCKED_FILL = PatternFill("solid", fgColor="EDEDED")
MONTH_LABELS = ["April", "May", "June", "July", "August", "September", "October", "November", "December",
                "January", "February", "March"]


def editable_fields(stage: str, lookups, is_setting_key) -> List[Tuple[Any, List[Any]]]:
    """(part, fields the teacher fills) for every part except Part B; settings fields are left out."""
    out = []
    for part in get_stage(stage).PARTS:
        if part.code == "B":
            continue
        fields = [f for f in part.fields(lookups) if not is_setting_key(f.key)]
        if fields:
            out.append((part, fields))
    return out


def exception_choices(stage: str, marks_subjects=None) -> Dict[str, str]:
    """Label shown in the Exceptions sheet -> the field it overrides for one student."""
    if marks_subjects is None:
        from backend.hpc.credit import summative_subjects
        marks_subjects = summative_subjects(stage)
    out = {f"Working days - {m}": f"a1_working_{i + 1}" for i, m in enumerate(MONTH_LABELS)}
    out["Medium of Instruction"] = "a1_medium"
    out["Rural/Urban"] = "a1_rural_urban"
    for n, subject in marks_subjects:
        out[f"Max marks - {subject}"] = f"d_{n}_max"
    return out


def build(path, stage: str, students: List[Dict[str, Any]], rows: Dict[str, Dict[str, Any]], lookups,
          settings: Dict[str, Any], marks_subjects, is_setting_key, part_b: Dict[str, Dict[str, Any]],
          problems: Dict[str, List[str]], summary: Dict[str, Any]):
    wb = Workbook()
    how = wb.active
    how.title = "How to use"
    _how_to(how, stage)
    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    ranges: Dict[tuple, str] = {}

    def list_range(options: List[str]) -> str:
        key = tuple(options)
        if key not in ranges:
            col = get_column_letter(len(ranges) + 1)
            for r, opt in enumerate(options, start=1):
                lists[f"{col}{r}"] = opt
            ranges[key] = f"Lists!${col}$1:${col}${max(len(options), 1)}"
        return ranges[key]

    settings_ws, max_cells, total_cell = _settings_sheet(wb, stage, settings, marks_subjects, summary)

    # ---- the stage sheet -------------------------------------------------
    ws = wb.create_sheet(stage, 1)
    groups = editable_fields(stage, lookups, is_setting_key)
    fixed = [("Student ID", ID_KEY, 12), ("Student Name", NAME_KEY, 26), ("Sync (Yes/No)", SYNC_KEY, 9),
             ("Problems when downloaded (not read back)", None, 40)]
    for c, (label, key, width) in enumerate(fixed, start=1):
        _head(ws, 1, c, "Student", "44546A")
        _head(ws, 2, c, label)
        ws.cell(row=3, column=c, value=key)
        ws.column_dimensions[get_column_letter(c)].width = width
    col = len(fixed) + 1
    columns: List[Tuple[int, Any]] = []
    present_cols: List[int] = []
    for g, (part, fields) in enumerate(groups):
        start = col
        for f in fields:
            _head(ws, 2, col, f.label, required=f.required)
            ws.cell(row=3, column=col, value=f.key)
            ws.column_dimensions[get_column_letter(col)].width = max(12, min(40, len(f.label) + 2))
            if f.kind in ("multi", "flags"):
                ws.cell(row=2, column=col).comment = Comment("Choose from: " + ", ".join(f.options), "HPC")
            elif f.max_len:
                ws.cell(row=2, column=col).comment = Comment(f"Up to {f.max_len} characters", "HPC")
            if f.key.startswith("a1_present_"):
                present_cols.append(col)
            columns.append((col, f))
            col += 1
            if f.key == "a1_present_12" and present_cols:                 # calculated, locked, never read back
                first, last = get_column_letter(present_cols[0]), get_column_letter(present_cols[-1])
                _head(ws, 2, col, "Attendance % (with the class working days)")
                ws.cell(row=3, column=col, value=None)
                ws.column_dimensions[get_column_letter(col)].width = 16
                for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + len(students)):
                    ws.cell(row=r, column=col, value=f"=IF({total_cell}>0,ROUND(SUM({first}{r}:{last}{r})/{total_cell}*100,2),\"\")")
                    ws.cell(row=r, column=col).fill = LOCKED_FILL
                col += 1
        title = "Marks obtained (HPC Credit)" if part.code == "D" else part.title
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=col - 1)
        _head(ws, 1, start, title, BAND_COLOURS[g % len(BAND_COLOURS)])
        ws.column_dimensions.group(get_column_letter(start), get_column_letter(col - 1), outline_level=1, hidden=False)

    last_row = FIRST_DATA_ROW + max(len(students), 1) - 1
    for r, s in enumerate(students, start=FIRST_DATA_ROW):
        sid = str(s[ID_KEY])
        values = rows.get(sid, {})
        ws.cell(row=r, column=1, value=sid)
        ws.cell(row=r, column=2, value=s.get(NAME_KEY, ""))
        ws.cell(row=r, column=3, value="Yes").protection = Protection(locked=False)
        found = problems.get(sid) or []
        ws.cell(row=r, column=4, value="; ".join(found) if found else "None").alignment = Alignment(wrap_text=True, vertical="top")
        for c, f in columns:
            cell = ws.cell(row=r, column=c, value=values.get(f.key, ""))
            cell.protection = Protection(locked=False)
        for c in (1, 2, 4):
            ws.cell(row=r, column=c).fill = LOCKED_FILL

    yes_no = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False)
    ws.add_data_validation(yes_no)
    yes_no.add(f"C{FIRST_DATA_ROW}:C{last_row}")
    for c, f in columns:
        letter = get_column_letter(c)
        if f.kind in ("choice", "onehot", "inlist") and f.options:
            v = DataValidation(type="list", formula1=f"={list_range(list(f.options))}", allow_blank=True)
        elif f.key.endswith("_obtained"):
            n = f.key.split("_")[1]
            v = DataValidation(type="decimal", operator="between", formula1="0", formula2=max_cells.get(n, "0"),
                               allow_blank=True, showErrorMessage=True, errorTitle="Marks",
                               error="Marks obtained must be between 0 and the max marks for this subject (Settings sheet).")
        elif f.kind == "int":
            v = DataValidation(type="whole", operator="between", formula1="0", formula2="31", allow_blank=True)
        elif f.max_len:
            v = DataValidation(type="textLength", operator="lessThanOrEqual", formula1=str(f.max_len), allow_blank=True,
                               showErrorMessage=True, errorTitle="Too long", error=f"Up to {f.max_len} characters.")
        else:
            continue
        ws.add_data_validation(v)
        v.add(f"{letter}{FIRST_DATA_ROW}:{letter}{last_row}")
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 48
    ws.row_dimensions[3].hidden = True
    ws.freeze_panes = f"E{FIRST_DATA_ROW}"
    _protect(ws)

    _exceptions_sheet(wb, students, exception_choices(stage, marks_subjects), list_range)
    _part_b_sheet(wb, stage, students, part_b)
    _summary_sheet(wb, stage, summary)
    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _head(ws, row, col, text, colour=None, required=False):
    cell = ws.cell(row=row, column=col, value=text)
    if colour:
        cell.font, cell.fill = WHITE_BOLD, PatternFill("solid", fgColor=colour)
    else:
        cell.font, cell.fill = Font(bold=True), (REQUIRED_FILL if required else HEAD_FILL)
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    return cell


def _protect(ws):
    """Locked cells cannot be changed; the teacher's cells were unlocked above. No password: a guide, not a secret."""
    ws.protection.sheet = True
    ws.protection.formatColumns = False          # widths may still be changed
    ws.protection.formatRows = False
    ws.protection.autoFilter = False


def _how_to(ws, stage):
    lines = [f"HPC class template - {stage}", "",
             f"1. The '{stage}' sheet has one row per student. Fill the white cells: parts A1, A2"
             + (", A3" if stage != "Foundational" else "") + (", A4" if stage == "Middle" else "")
             + ", C" + (" and the marks obtained" if stage != "Foundational" else "") + ".",
             "2. Grey cells and the grey sheets (Part B, Settings, Class summary) are filled from the web app and",
             "   are not read back. Part B and the class settings always come from the web app.",
             "3. A student who needs something different from the class settings (working days, medium,",
             "   rural/urban, max marks): add a row on the 'Exceptions' sheet.",
             "4. Set Sync to 'No' for anyone you do not want uploaded yet.",
             "5. The Problems column shows what was missing when the file was made (it is not read back).",
             "6. Upload the file on 'Validate & Upload'. Every student is checked again; anyone who is not",
             "   ready is listed and skipped, the others are saved."]
    for i, line in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=line).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    ws.column_dimensions["A"].width = 100
    ws["A19"], ws["A20"] = "Stages in this file (do not edit):", stage
    ws["A19"].font = ws["A20"].font = Font(color="808080")
    _protect(ws)


def _settings_sheet(wb, stage, settings, marks_subjects, summary):
    ws = wb.create_sheet(SETTINGS_SHEET)
    ws["A1"] = f"Class settings for {stage} (from the web app; change them there)"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = f"Saved: {summary.get('settings_saved_at') or '-'}"
    rows = [("Medium of Instruction", settings.get("medium", "")), ("Rural/Urban", settings.get("rural_urban", ""))]
    days = settings.get("working_days") or [None] * 12
    rows += [(f"Working days - {m}", d) for m, d in zip(MONTH_LABELS, days)]
    rows.append(("Working days - total", None))
    max_cells = {}
    for n, subject in marks_subjects:
        rows.append((f"Max marks - {subject}", (settings.get("max_marks") or {}).get(n)))
    rows.append(("Declaration", settings.get("declaration", "")))
    total_cell = ""
    first = 4
    for i, (label, value) in enumerate(rows, start=first):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        if label == "Working days - total":
            ws.cell(row=i, column=2, value=f"=SUM(B{first + 2}:B{first + 13})")
            total_cell = f"'{SETTINGS_SHEET}'!$B${i}"
        else:
            ws.cell(row=i, column=2, value=value)
        if label.startswith("Max marks - "):
            n = next(n for n, s in marks_subjects if s == label[len("Max marks - "):])
            max_cells[n] = f"'{SETTINGS_SHEET}'!$B${i}"
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 18
    _protect(ws)
    return ws, max_cells, total_cell


def _exceptions_sheet(wb, students, choices, list_range):
    ws = wb.create_sheet(EXCEPTIONS_SHEET)
    heads = [("Student ID", 14), ("What is different for this student", 40), ("Value", 16), ("Note (not read)", 40)]
    for c, (label, width) in enumerate(heads, start=1):
        _head(ws, 1, c, label)
        ws.column_dimensions[get_column_letter(c)].width = width
    ids = [str(s[ID_KEY]) for s in students] or [""]
    v_id = DataValidation(type="list", formula1=f"={list_range(ids)}", allow_blank=True)
    v_what = DataValidation(type="list", formula1=f"={list_range(list(choices))}", allow_blank=True)
    ws.add_data_validation(v_id)
    ws.add_data_validation(v_what)
    v_id.add("A2:A300")
    v_what.add("B2:B300")
    ws.freeze_panes = "A2"


def _part_b_sheet(wb, stage, students, part_b):
    ws = wb.create_sheet(PART_B_SHEET)
    st = get_stage(stage)
    names = dict(zip(st.DOMAINS, st.SUBJECTS))
    answer_labels = []
    for info in part_b.values():
        for label, _ in info.get("answers", []):
            if label not in answer_labels:
                answer_labels.append(label)
    heads = ["Student ID", "Student Name"]
    for d in st.DOMAINS:
        heads += [f"{names[d]}: activity", f"{names[d]}: levels (Awareness/Sensitivity/Creativity)"]
    heads += answer_labels
    ws.cell(row=1, column=1, value="Part B - set on the web app (read only, never read back)").font = Font(bold=True, size=12)
    for c, h in enumerate(heads, start=1):
        _head(ws, 2, c, h)
        ws.column_dimensions[get_column_letter(c)].width = 14 if c == 1 else 28
    for r, s in enumerate(students, start=3):
        sid = str(s[ID_KEY])
        info = part_b.get(sid, {})
        values = [sid, s.get(NAME_KEY, "")]
        for d in st.DOMAINS:
            subj = (info.get("subjects") or {}).get(d, {})
            values += [subj.get("activity", ""), subj.get("levels", "")]
        answers = dict(info.get("answers", []))
        values += [answers.get(label, "") for label in answer_labels]
        for c, v in enumerate(values, start=1):
            ws.cell(row=r, column=c, value=v).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C3"
    _protect(ws)


def _summary_sheet(wb, stage, summary):
    ws = wb.create_sheet(SUMMARY_SHEET)
    facts = [("Made at", summary.get("generated_at")), ("Stage", stage), ("Classes", summary.get("classes")),
             ("Part B ready as of", summary.get("ready_as_of")), ("Class settings saved at", summary.get("settings_saved_at")),
             ("Students in this file", summary.get("included_count")), ("Students not in this file", summary.get("excluded_count")),
             ("Who is in the file", summary.get("rule"))]
    ws["A1"] = "Class summary (made by the web app; not read back except the list of students below)"
    ws["A1"].font = Font(bold=True, size=12)
    for i, (label, value) in enumerate(facts, start=3):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        ws.cell(row=i, column=2, value=value)
    start = len(facts) + 5
    for c, h in enumerate(["Student ID", "In this file", "Part B", "Other problems when downloaded"], start=1):
        _head(ws, start, c, h)
    for r, item in enumerate(summary.get("students", []), start=start + 1):
        ws.cell(row=r, column=1, value=item["student_id"])
        ws.cell(row=r, column=2, value="Yes" if item["in_file"] else "No")
        ws.cell(row=r, column=3, value="Ready" if item["ready"] else "Not ready: " + "; ".join(item["part_b_problems"]))
        ws.cell(row=r, column=4, value="; ".join(item["other_problems"]) or "None")
        for c in (3, 4):
            ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
    for c, w in zip("ABCD", (14, 12, 60, 60)):
        ws.column_dimensions[c].width = w
    ws["F3"], ws["G3"] = "summary_start_row", start                 # where the list starts (for reading back)
    ws.column_dimensions["F"].hidden = ws.column_dimensions["G"].hidden = True
    _protect(ws)


def read_exceptions(wb, stage: str, known_ids) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """{student_id: {field key: value}} from the Exceptions sheet, and problems with rows that cannot be used."""
    out: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    if EXCEPTIONS_SHEET not in wb.sheetnames:
        return out, problems
    choices = exception_choices(stage)
    for r, (sid, what, value, *_rest) in enumerate(wb[EXCEPTIONS_SHEET].iter_rows(min_row=2, values_only=True), start=2):
        if sid in (None, "") and what in (None, "") and value in (None, ""):
            continue
        sid = str(sid or "").split(".")[0].strip()
        if sid not in known_ids:
            problems.append(f"Exceptions row {r}: student ID '{sid}' is not in this file - row ignored.")
            continue
        if what not in choices:
            problems.append(f"Exceptions row {r} (student {sid}): '{what}' is not one of the choices - row ignored.")
            continue
        if value in (None, ""):
            problems.append(f"Exceptions row {r} (student {sid}): no value given for '{what}' - row ignored.")
            continue
        out.setdefault(sid, {})[choices[what]] = value
    return out, problems


def info(wb) -> Dict[str, Any]:
    """Facts a template carries for the upload check: when Part B was ready, and who was in the file."""
    if SUMMARY_SHEET not in wb.sheetnames:
        return {"is_template": False}
    ws = wb[SUMMARY_SHEET]
    facts = {str(ws.cell(row=r, column=1).value): ws.cell(row=r, column=2).value for r in range(3, 12)}
    start = int(ws["G3"].value or 0)
    included = []
    for row in ws.iter_rows(min_row=start + 1, values_only=True) if start else []:
        if row[0] not in (None, "") and str(row[1]) == "Yes":
            included.append(str(row[0]))
    return {"is_template": True, "stage": facts.get("Stage"), "ready_as_of": facts.get("Part B ready as of"),
            "made_at": facts.get("Made at"), "included": included}


def part_b_view(stage: str, row: Dict[str, Any], lookups, labels: Dict[str, str]) -> Dict[str, Any]:
    """What the locked Part B sheet shows for a student: each subject's activity and levels, and the answers."""
    st = get_stage(stage)
    short = {"Beginner": "B", "Proficient": "P", "Advanced": "A"}
    subjects = {}
    for d in st.DOMAINS:
        key = str(row.get(activity_grid.act_key(d)) or "")
        levels = "/".join(short.get(str(row.get(activity_grid.level_key(d, a)) or ""), "-") for a, _ in activity_grid.ABILITIES)
        subjects[d] = {"activity": labels.get(key, key), "levels": levels}
    part_b = next(p for p in st.PARTS if p.code == "B")
    answers = [(f.label, row.get(f.key, "")) for f in part_b.fields(lookups)]
    return {"subjects": subjects, "answers": answers}
