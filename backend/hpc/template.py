"""
The class template: what the teacher fills in Excel once the dashboard has done the rest.

Sheets
  How to use                 instructions (A20 = the stage, as in every workbook from this app)
  <Stage>                    one row per student (only students whose Part B is complete, unless the teacher
                             chose "all"): Sync, then parts A1, A2 (A3, A4), C and the marks obtained, each part
                             its own colour and a collapsible column group. Row 1 = part, row 2 = column header,
                             row 3 = field key (hidden; how the file is read back). Problems show as live cell
                             colours (red = wrong, yellow = still to fill). Only the teacher's cells are unlocked.
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
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from backend.hpc.stages import activity_grid, get_stage

ID_KEY, NAME_KEY, SYNC_KEY = "student_id", "student_name", "sync"
SUMMARY_SHEET, SETTINGS_SHEET, PART_B_SHEET, EXCEPTIONS_SHEET = "Class summary", "Settings", "Part B (from dashboard)", "Exceptions"
LOCKED_SHEETS = ("How to use", "Lists", SUMMARY_SHEET, SETTINGS_SHEET, PART_B_SHEET, EXCEPTIONS_SHEET)
FIRST_DATA_ROW = 4
# The look: one calm colour per part (a strong title bar over a soft header), white cells to fill with light
# borders and gentle striping, quiet grey for what the web app filled in, soft red / yellow for problems.
FONT = "Calibri"
INK, MUTED, LINE = "1F2937", "6B7280", "E5E7EB"
PART_COLOURS = {"A1": ("4F46E5", "EEF2FF"), "A2": ("0D9488", "F0FDFA"), "A3": ("D97706", "FFFBEB"),
                "A4": ("DB2777", "FDF2F8"), "C": ("0284C7", "F0F9FF"), "D": ("7C3AED", "F5F3FF")}
STUDENT_COLOURS = ("334155", "F1F5F9")
WHITE_BOLD = Font(name=FONT, bold=True, color="FFFFFF", size=12)
HEAD_FILL = PatternFill("solid", fgColor="F1F5F9")
LOCKED_FILL = PatternFill("solid", fgColor="F1F5F9")
STRIPE_FILL = PatternFill("solid", fgColor="FAFAFB")
THIN = Side(style="thin", color=LINE)
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
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


def sheet_names(stage: str, combined: bool) -> Dict[str, str]:
    """A one-stage file keeps the short names; a file for several stages names each stage's own sheets."""
    if not combined:
        return {"settings": SETTINGS_SHEET, "exceptions": EXCEPTIONS_SHEET, "part_b": PART_B_SHEET}
    return {"settings": f"{stage} - Settings", "exceptions": f"{stage} - Exceptions", "part_b": f"{stage} - Part B"}


def is_locked_sheet(title: str) -> bool:
    """Sheets that are never read as student data (their own readers handle Exceptions)."""
    return title in LOCKED_SHEETS or title.endswith((" - Settings", " - Exceptions", " - Part B"))


def build(path, stage: str, students: List[Dict[str, Any]], rows: Dict[str, Dict[str, Any]], lookups,
          settings: Dict[str, Any], marks_subjects, is_setting_key, part_b: Dict[str, Dict[str, Any]],
          problems: Dict[str, List[str]], summary: Dict[str, Any]):
    """The class template for one stage."""
    return build_many(path, [{"stage": stage, "students": students, "rows": rows, "lookups": lookups, "settings": settings,
                              "marks_subjects": marks_subjects, "is_setting_key": is_setting_key, "part_b": part_b,
                              "problems": problems}], summary)


def build_many(path, sections: List[Dict[str, Any]], summary: Dict[str, Any]):
    """One file for one or more stages: a sheet to fill per stage (sheet 1, 2, 3 ...), each stage with its own
    Settings, Exceptions and Part B sheets, one How to use and one Class summary."""
    combined = len(sections) > 1
    stages = [sec["stage"] for sec in sections]
    wb = Workbook()
    how = wb.active
    how.title = "How to use"
    _how_to(how, stages)
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

    for i, sec in enumerate(sections):
        _stage_sheets(wb, sec, sheet_names(sec["stage"], combined), list_range, summary, position=1 + i)
    _summary_sheet(wb, ", ".join(stages), summary)
    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _stage_sheets(wb, sec: Dict[str, Any], names: Dict[str, str], list_range, summary: Dict[str, Any], position: int) -> None:
    stage, students, rows, lookups = sec["stage"], sec["students"], sec["rows"], sec["lookups"]
    settings, marks_subjects, is_setting_key = sec["settings"], sec["marks_subjects"], sec["is_setting_key"]
    part_b, problems = sec["part_b"], sec["problems"]
    settings_ws, max_cells, total_cell = _settings_sheet(wb, stage, settings, marks_subjects, summary, names["settings"])

    # ---- the stage sheet -------------------------------------------------
    ws = wb.create_sheet(stage, position)
    ws.sheet_properties.tabColor = PART_COLOURS["A1"][0]
    ws.sheet_view.showGridLines = False
    groups = editable_fields(stage, lookups, is_setting_key)
    fixed = [("Student ID", ID_KEY, 12), ("Student name", NAME_KEY, 28), ("Sync", SYNC_KEY, 8)]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(fixed))
    _band(ws, 1, "Student", *STUDENT_COLOURS)
    for c, (label, key, width) in enumerate(fixed, start=1):
        _head(ws, 2, c, label, STUDENT_COLOURS)
        ws.cell(row=3, column=c, value=key)
        ws.column_dimensions[get_column_letter(c)].width = width
    col = len(fixed) + 1
    columns: List[Tuple[int, Any]] = []
    present_cols: List[int] = []
    for g, (part, fields) in enumerate(groups):
        start = col
        colours = PART_COLOURS.get(part.code, STUDENT_COLOURS)
        for f in fields:
            _head(ws, 2, col, _short_label(part, f) + (" *" if f.required else ""), colours)
            ws.cell(row=3, column=col, value=f.key)
            ws.column_dimensions[get_column_letter(col)].width = _width(f)
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
                _head(ws, 2, col, "Attendance %", colours)
                ws.cell(row=3, column=col, value=None)
                ws.column_dimensions[get_column_letter(col)].width = 12
                for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + len(students)):
                    pct = ws.cell(row=r, column=col, value=f"=IF({total_cell}>0,ROUND(SUM({first}{r}:{last}{r})/{total_cell}*100,1),\"\")")
                    pct.fill, pct.border, pct.number_format = LOCKED_FILL, CELL_BORDER, '0.0"%"'
                    pct.font, pct.alignment = Font(name=FONT, color=MUTED, bold=True), Alignment(horizontal="center", vertical="center")
                col += 1
        title = "Marks obtained (HPC Credit)" if part.code == "D" else part.title
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=col - 1)
        _band(ws, start, title, *colours)
        ws.column_dimensions.group(get_column_letter(start), get_column_letter(col - 1), outline_level=1, hidden=False)

    last_row = FIRST_DATA_ROW + max(len(students), 1) - 1
    for r, s in enumerate(students, start=FIRST_DATA_ROW):
        sid = str(s[ID_KEY])
        values = rows.get(sid, {})
        stripe = STRIPE_FILL if (r - FIRST_DATA_ROW) % 2 else None   # no fixed height: rows grow with wrapped text
        for c, value, bold in ((1, sid, False), (2, s.get(NAME_KEY, ""), True)):
            cell = ws.cell(row=r, column=c, value=value)
            cell.fill, cell.border = LOCKED_FILL, CELL_BORDER
            cell.font = Font(name=FONT, color=MUTED if c == 1 else INK, bold=bold)
            cell.alignment = Alignment(vertical="center")
        sync = ws.cell(row=r, column=3, value="Yes")
        _input(sync, stripe, center=True)
        for c, f in columns:
            _input(ws.cell(row=r, column=c, value=values.get(f.key, "")), stripe,
                   center=f.kind in ("int", "choice", "inlist", "onehot") or f.key.endswith(("_obtained", "_max")),
                   wrap=f.kind in ("text", "multi", "flags"))
        not_ready = problems.get(sid) or []
        if not_ready:                                  # "all students" file: Part B is set on the web app, not here
            name = ws.cell(row=r, column=2)
            name.fill = BAD_FILL
            name.comment = Comment("Part B not ready (fix it on the web app's Activities tab; this student is "
                                   "skipped on upload until then):\n" + "\n".join(not_ready), "HPC")

    yes_no = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False, showInputMessage=True,
                            promptTitle="Sync", prompt="Yes = upload this student. No = leave them out for now.")
    ws.add_data_validation(yes_no)
    yes_no.add(f"C{FIRST_DATA_ROW}:C{last_row}")
    for c, f in columns:
        letter = get_column_letter(c)
        hint = dict(showInputMessage=True, promptTitle=_short_label(None, f)[:32])
        if f.kind in ("choice", "onehot", "inlist") and f.options:
            v = DataValidation(type="list", formula1=f"={list_range(list(f.options))}", allow_blank=True,
                               showErrorMessage=False,           # short forms are allowed (read back in full)
                               prompt="Pick from the list, or type the first letters (for example n = No, "
                                      "prof = Proficient).", **hint)
        elif f.key.endswith("_obtained"):
            n = f.key.split("_")[1]
            v = DataValidation(type="decimal", operator="between", formula1="0", formula2=max_cells.get(n, "0"),
                               allow_blank=True, showErrorMessage=True, errorTitle="Marks",
                               error="Marks obtained must be between 0 and the max marks for this subject (Settings sheet).",
                               prompt="Marks obtained: from 0 up to the max marks on the Settings sheet.", **hint)
        elif f.kind == "int":
            v = DataValidation(type="whole", operator="between", formula1="0", formula2="31", allow_blank=True,
                               prompt="A whole number of days (0-31); not more than the working days.", **hint)
        elif f.max_len:
            v = DataValidation(type="textLength", operator="lessThanOrEqual", formula1=str(f.max_len), allow_blank=True,
                               showErrorMessage=True, errorTitle="Too long", error=f"Up to {f.max_len} characters.",
                               prompt=f"Up to {f.max_len} characters." + (" Separate several with commas." if f.kind in ("multi", "flags") else ""),
                               **hint)
        else:
            continue
        ws.add_data_validation(v)
        v.add(f"{letter}{FIRST_DATA_ROW}:{letter}{last_row}")
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 54
    ws.row_dimensions[3].hidden = True
    ws.sheet_view.zoomScale = 100
    _highlights(ws, columns, FIRST_DATA_ROW, last_row, max_cells, {str(n): subject for n, subject in marks_subjects},
                list_range, names)
    ws.freeze_panes = f"D{FIRST_DATA_ROW}"
    _protect(ws)

    _exceptions_sheet(wb, students, exception_choices(stage, marks_subjects), list_range, names["exceptions"])
    _part_b_sheet(wb, stage, students, part_b, names["part_b"])


def _head(ws, row, col, text, colours=STUDENT_COLOURS):
    """A column header: bold text on the part's soft colour, with the part's colour as a line underneath."""
    cell = ws.cell(row=row, column=col, value=text)
    strong, soft = colours
    cell.font = Font(name=FONT, bold=True, color=INK, size=10)
    cell.fill = PatternFill("solid", fgColor=soft)
    cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=Side(style="medium", color=strong))
    return cell


def _band(ws, col, text, strong, soft):
    """A part's title bar (row 1)."""
    cell = ws.cell(row=1, column=col, value=text)
    cell.font, cell.fill = WHITE_BOLD, PatternFill("solid", fgColor=strong)
    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    return cell


def _input(cell, stripe=None, center=False, wrap=False):
    """A cell the teacher fills: unlocked, white (or a faint stripe), light border; text wraps onto more lines."""
    cell.protection = Protection(locked=False)
    cell.border = CELL_BORDER
    cell.font = Font(name=FONT, color=INK)
    cell.alignment = Alignment(horizontal="center" if center else "left", vertical="center", wrap_text=wrap)
    if stripe is not None:
        cell.fill = stripe


def _short_label(part, f) -> str:
    """Headers without the part's name in front (the title bar says it): "Attendance May: days present" ->
    "May\ndays present"; "Language 1 (R1): Awareness" -> "Language 1 (R1)\nAwareness"."""
    label = f.label[len("Attendance "):] if f.label.startswith("Attendance ") else f.label
    if f.key.endswith("_obtained"):
        return label.split(":")[0]                   # the title bar says "Marks obtained"
    label = label.replace("/", " / ") if label.count("/") > 1 else label
    head, sep, tail = label.partition(": ")
    return f"{head}\n{tail}" if sep else label


def _width(f) -> int:
    if f.kind == "int":
        return 10
    if f.key.endswith(("_obtained", "_max")):
        return 14
    if f.kind in ("choice", "inlist", "onehot"):
        return 18
    if f.kind in ("multi", "flags"):
        return 26
    return max(24, min(36, (f.max_len or 60) // 3 + 12))


def _protect(ws):
    """Locked cells (IDs, names, the hidden key row) cannot be changed; the teacher's cells were unlocked above.
    Formatting stays allowed - wrap text, row heights, column widths, colours. No password: a guide, not a secret."""
    ws.protection.sheet = True
    ws.protection.formatCells = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False
    ws.protection.autoFilter = False


def _how_to(ws, stages):
    """A friendly first page: what to do, in order, and what the colours mean."""
    stages = [stages] if isinstance(stages, str) else list(stages)
    stage = stages[0] if len(stages) == 1 else " / ".join(stages)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "16A34A"
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 6
    ws.column_dimensions["C"].width = 96
    ws.merge_cells("B2:C2")
    ws["B2"] = f"HPC class template  -  {stage}"
    ws["B2"].font = Font(name=FONT, bold=True, size=20, color="FFFFFF")
    ws["B2"].fill = PatternFill("solid", fgColor=PART_COLOURS["A1"][0])
    ws["B2"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[2].height = 40
    ws.merge_cells("B3:C3")
    ws["B3"] = "Fill the white cells, upload the file, done. Everything else comes from the web app."
    ws["B3"].font = Font(name=FONT, italic=True, color=MUTED, size=11)
    parts = "A1, A2" + (", A3" if stages != ["Foundational"] else "") + (", A4" if "Middle" in stages else "") + ", C"
    sheets = f"the '{stages[0]}' sheet" if len(stages) == 1 else "each stage's sheet (" + ", ".join(f"'{x}'" for x in stages) + ")"
    steps = [
        f"Open {sheets}. One row per student. Fill the white cells: parts {parts}"
        + (" and the marks obtained." if stages != ["Foundational"] else "."),
        "Click a cell to see a short hint. For a list, pick from the dropdown or just type the first letters "
        "(n = No, y = Yes, prof = Proficient, adv = Advanced); the upload turns them into the full answer.",
        "Grey cells and the grey sheets (Part B, Settings, Class summary) come from the web app and are not read back.",
        "A student who is different from the class settings (working days, medium, rural/urban, max marks)? "
        + ("Add a row on the 'Exceptions' sheet." if len(stages) == 1 else "Add a row on that stage's Exceptions sheet."),
        "Set Sync to 'No' for anyone you do not want to upload yet.",
        "Upload the file on 'Download & Upload'. Everyone is checked again; anyone not ready is skipped and listed.",
    ]
    r = 5
    for i, text in enumerate(steps, start=1):
        num = ws.cell(row=r, column=2, value=i)
        num.font = Font(name=FONT, bold=True, size=14, color=PART_COLOURS["A1"][0])
        num.alignment = Alignment(horizontal="center", vertical="center")
        cell = ws.cell(row=r, column=3, value=text)
        cell.font = Font(name=FONT, size=11, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[r].height = 30
        r += 1
    r += 1
    ws.cell(row=r, column=2, value="What the colours mean").font = Font(name=FONT, bold=True, size=13, color=INK)
    r += 1
    legend = [(None, "A cell for you to fill."),
              (TODO_FILL, "Still empty, and it must be filled."),
              (BAD_FILL, "Not right yet (for example days present more than the working days, marks above the max marks, "
                         "text too long). The colour goes away as soon as it is right."),
              (LOCKED_FILL, "Filled by the web app; you cannot change it here. A red student name: Part B is not ready "
                            "(point at the name to see why).")]
    for fill, text in legend:
        swatch = ws.cell(row=r, column=2)
        swatch.border = CELL_BORDER
        if fill is not None:
            swatch.fill = fill
        cell = ws.cell(row=r, column=3, value=text)
        cell.font = Font(name=FONT, size=11, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="center", indent=1)
        ws.row_dimensions[r].height = 30
        r += 1
    # The stage, where every workbook from this app keeps it (read back; invisible here).
    ws["A19"], ws["A20"] = "Stages in this file (do not edit):", ", ".join(stages)
    ws["A19"].font = ws["A20"].font = Font(color="FFFFFF", size=1)
    _protect(ws)


def _settings_sheet(wb, stage, settings, marks_subjects, summary, sheet_name=SETTINGS_SHEET):
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "64748B"
    ws["A1"] = f"Class settings - {stage}"
    ws["A1"].font = Font(name=FONT, bold=True, size=16, color=INK)
    ws["A2"] = f"From the web app (change them there). Saved: {summary.get('settings_saved_at') or '-'}"
    ws["A2"].font = Font(name=FONT, italic=True, color=MUTED)
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
        name = ws.cell(row=i, column=1, value=label)
        name.font = Font(name=FONT, bold=True, color=INK)
        if label == "Working days - total":
            cell = ws.cell(row=i, column=2, value=f"=SUM(B{first + 2}:B{first + 13})")
            total_cell = f"'{sheet_name}'!$B${i}"
            cell.font = Font(name=FONT, bold=True, color=PART_COLOURS["A1"][0])
        else:
            cell = ws.cell(row=i, column=2, value=value)
            cell.font = Font(name=FONT, color=INK)
        stripe = LOCKED_FILL if (i - first) % 2 == 0 else None
        for c in (name, cell):
            c.border = CELL_BORDER
            if stripe is not None:
                c.fill = stripe
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[i].height = 20
        if label.startswith("Max marks - "):
            n = next(n for n, s in marks_subjects if s == label[len("Max marks - "):])
            max_cells[n] = f"'{sheet_name}'!$B${i}"
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 20
    _protect(ws)
    return ws, max_cells, total_cell


def _exceptions_sheet(wb, students, choices, list_range, name=EXCEPTIONS_SHEET):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = PART_COLOURS["A3"][0]
    heads = [("Student ID", 14), ("What is different for this student", 40), ("Value", 16), ("Note (not read)", 40)]
    for c, (label, width) in enumerate(heads, start=1):
        _head(ws, 1, c, label, PART_COLOURS["A3"])
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[1].height = 30
    for r in range(2, 41):                            # a tidy area to fill; more rows can be used below it
        for c in range(1, 5):
            _input(ws.cell(row=r, column=c), STRIPE_FILL if r % 2 else None, center=c in (1, 3))
        ws.row_dimensions[r].height = 20
    ids = [str(s[ID_KEY]) for s in students] or [""]
    v_id = DataValidation(type="list", formula1=f"={list_range(ids)}", allow_blank=True, showInputMessage=True,
                          promptTitle="Student ID", prompt="Pick the student (IDs are on the class sheet).")
    v_what = DataValidation(type="list", formula1=f"={list_range(list(choices))}", allow_blank=True, showInputMessage=True,
                            promptTitle="What is different", prompt="Pick what is different for this student.")
    ws.add_data_validation(v_id)
    ws.add_data_validation(v_what)
    v_id.add("A2:A300")
    v_what.add("B2:B300")
    ws.freeze_panes = "A2"


def _part_b_sheet(wb, stage, students, part_b, name=PART_B_SHEET):
    ws = wb.create_sheet(name)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = PART_COLOURS["C"][0]
    st = get_stage(stage)
    names = dict(zip(st.DOMAINS, st.SUBJECTS))
    answer_labels = []
    for info in part_b.values():
        for label, _ in info.get("answers", []):
            if label not in answer_labels:
                answer_labels.append(label)
    heads = ["Student ID", "Student name"]
    for d in st.DOMAINS:
        heads += [f"{names[d]}\nactivity", f"{names[d]}\nlevels (A/S/C)"]
    heads += answer_labels
    ws.cell(row=1, column=1, value=f"Part B - {stage} - set on the web app (read only)").font = Font(name=FONT, bold=True, size=14, color=INK)
    for c, h in enumerate(heads, start=1):
        _head(ws, 2, c, h, PART_COLOURS["C"])
        ws.column_dimensions[get_column_letter(c)].width = 12 if c == 1 else (11 if "levels" in h else 28)
    ws.row_dimensions[2].height = 44
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
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name=FONT, color=INK, bold=(c == 2))
            cell.border = CELL_BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="center" if c == 1 else "left")
            if (r - 3) % 2:
                cell.fill = STRIPE_FILL
    ws.freeze_panes = "C3"
    _protect(ws)


# Both colours set: conditional formatting in Excel uses the background one, a normal cell the foreground one.
BAD_FILL = PatternFill("solid", start_color="FECACA", end_color="FECACA")
TODO_FILL = PatternFill("solid", start_color="FEF3C7", end_color="FEF3C7")
BAD_FONT = Font(color="991B1B", bold=True)
SETTINGS_FIRST_MONTH_ROW = 6                     # Settings sheet: B6..B17 are the working days April..March


def _effective(sid_cell: str, what: str, default: str, exceptions: str = EXCEPTIONS_SHEET) -> str:
    """This student's value from the Exceptions sheet when there is one, else the class setting."""
    ex = f"'{exceptions}'"
    return (f'IF(COUNTIFS({ex}!$A:$A,{sid_cell},{ex}!$B:$B,"{what}")>0,'
            f'SUMIFS({ex}!$C:$C,{ex}!$A:$A,{sid_cell},{ex}!$B:$B,"{what}"),{default})')


def _highlights(ws, columns, first: int, last: int, max_cells: Dict[str, str], marks_label: Dict[str, str],
                list_range, names: Dict[str, str] = None) -> None:
    """Live colours, worked out by Excel: red where a value is wrong, yellow where a required one is missing."""
    from openpyxl.formatting.rule import FormulaRule
    names = names or sheet_names("", False)
    sid = f"$A{first}"
    for c, f in columns:
        letter = get_column_letter(c)
        cell, area = f"{letter}{first}", f"{letter}{first}:{letter}{last}"
        bad = []
        if f.key.startswith("a1_present_"):
            month = int(f.key.rsplit("_", 1)[1])
            days = _effective(sid, f"Working days - {MONTH_LABELS[month - 1]}",
                              f"'{names['settings']}'!$B${SETTINGS_FIRST_MONTH_ROW + month - 1}", names["exceptions"])
            bad.append(f"AND(ISNUMBER({cell}),{cell}>{days})")
        elif f.key.endswith("_obtained"):
            n = f.key.split("_")[1]
            top = _effective(sid, f"Max marks - {marks_label.get(n, '')}", max_cells.get(n, "0"), names["exceptions"])
            bad.append(f"AND(ISNUMBER({cell}),OR({cell}<0,{cell}>{top}))")
        if f.max_len:
            bad.append(f"LEN({cell})>{f.max_len}")
        if f.kind in ("choice", "inlist", "onehot") and f.options:
            options = list_range(list(f.options))       # wrong unless an option or the start of exactly one
            bad.append(f'AND(LEN({cell})>0,COUNTIF({options},{cell})=0,COUNTIF({options},{cell}&"*")<>1)')
        for rule in bad:
            ws.conditional_formatting.add(area, FormulaRule(formula=[rule], fill=BAD_FILL, font=BAD_FONT, stopIfTrue=True))
        if f.required:
            ws.conditional_formatting.add(area, FormulaRule(formula=[f'AND($C{first}<>"No",LEN(TRIM({cell}))=0)'],
                                                            fill=TODO_FILL))



def _summary_sheet(wb, stage, summary):
    ws = wb.create_sheet(SUMMARY_SHEET)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "94A3B8"
    facts = [("Made at", summary.get("generated_at")), ("Stage", stage), ("Classes", summary.get("classes")),
             ("Part B ready as of", summary.get("ready_as_of")), ("Class settings saved at", summary.get("settings_saved_at")),
             ("Students in this file", summary.get("included_count")), ("Students not in this file", summary.get("excluded_count")),
             ("Who is in the file", summary.get("rule"))]
    ws["A1"] = "Class summary"
    ws["A1"].font = Font(name=FONT, bold=True, size=16, color=INK)
    for i, (label, value) in enumerate(facts, start=3):
        ws.cell(row=i, column=1, value=label).font = Font(name=FONT, bold=True, color=INK)
        ws.cell(row=i, column=2, value=value).font = Font(name=FONT, color=INK)
    start = len(facts) + 5
    for c, h in enumerate(["Student ID", "In this file", "Part B", "Other problems when downloaded", "Stage"], start=1):
        _head(ws, start, c, h)
    for r, item in enumerate(summary.get("students", []), start=start + 1):
        values = [item["student_id"], "Yes" if item["in_file"] else "No",
                  "Ready" if item["ready"] else "Not ready: " + "; ".join(item["part_b_problems"]),
                  "; ".join(item["other_problems"]) or "None", item.get("stage", stage)]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name=FONT, color=INK if c != 4 else MUTED)
            cell.border = CELL_BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="center" if c < 3 else "left")
            if (r - start) % 2 == 0:
                cell.fill = STRIPE_FILL
    for c, w in zip("ABCDE", (14, 12, 60, 60, 14)):
        ws.column_dimensions[c].width = w
    ws["F3"], ws["G3"] = "summary_start_row", start                 # where the list starts (for reading back)
    ws.column_dimensions["F"].hidden = ws.column_dimensions["G"].hidden = True
    _protect(ws)


def read_exceptions(wb, stage: str, known_ids, sheet: str = EXCEPTIONS_SHEET) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """{student_id: {field key: value}} from a stage's Exceptions sheet, and problems with rows that cannot be used."""
    out: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    if sheet not in wb.sheetnames:
        return out, problems
    choices = exception_choices(stage)
    for r, (sid, what, value, *_rest) in enumerate(wb[sheet].iter_rows(min_row=2, values_only=True), start=2):
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
    stage_text = str(facts.get("Stage") or "")
    return {"is_template": True, "stage": stage_text, "stages": [x.strip() for x in stage_text.split(",") if x.strip()],
            "ready_as_of": facts.get("Part B ready as of"), "made_at": facts.get("Made at"), "included": included}


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
