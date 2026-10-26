"""
Excel workbook for one teacher: every stage they teach in one file.

Layout:
  How to use     - instructions (cell A20 lists the stages in the file)
  Students       - one row per student with its Stage and a Sync (Yes/No) column
  <Stage> <part> - one sheet per stage and HPC part (e.g. "Prep A1", "Middle B"), one row per
                   student, prefilled with what the portal currently holds. Row 1 = readable
                   header, row 2 = field key (hidden; it is how the file is read back).
  Lists          - hidden; dropdown values
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from backend.hpc.stages import get_stage
from backend.hpc.stages.common import Lookups

ID_KEY, NAME_KEY, SYNC_KEY, STAGE_KEY = "student_id", "student_name", "sync", "stage"
SHEET_PREFIX = {"Foundational": "Found.", "Preparatory": "Prep", "Middle": "Middle"}
SUMMARY_HEADER = "Activities and levels (set on the Activities tab - read only)"
SUMMARY_FILL = PatternFill("solid", fgColor="E7E6E6")
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
REQUIRED_FILL = PatternFill("solid", fgColor="C00000")

HOW_TO = [
    "HPC class workbook - how to use",
    "",
    "1. 'Students' lists all your students with their stage. Set Sync to 'No' for anyone you",
    "   don't want uploaded yet.",
    "2. Each part sheet (e.g. 'Prep A1', 'Middle B', 'Found. C') has one row per student of that",
    "   stage, already filled with what the portal holds today. Fill or correct the cells; leave",
    "   a cell as it is to keep it.",
    "3. Red headers are required by the portal before a part can be completed.",
    "4. Cells with a dropdown only accept the listed values. Columns marked '(comma separated)'",
    "   take several values from the list in the header note.",
    "5. Don't change the Student ID column or the hidden second row.",
    "   Part B activities and their levels are chosen on the web app's Activities tab; the grey",
    "   column in each Part B sheet only shows them (changes there are not read).",
    "6. Upload the file back. It is checked first: students with errors are listed and nothing is",
    "   written for them. The others are saved part by part and marked complete.",
]


@dataclass
class Section:
    """One stage's part of the workbook."""
    stage: str                                 # "Foundational" | "Preparatory" | "Middle"
    students: List[Dict[str, Any]]             # roster entries (student_id, student_name, ...)
    rows: Dict[str, Dict[str, Any]]            # student_id -> {field key: value}
    lookups: Lookups
    activity_summaries: Dict[str, str] = field(default_factory=dict)   # student_id -> Part B summary text


def build(sections: List[Section], path: Path) -> Path:
    wb = Workbook()
    how = wb.active
    how.title = "How to use"
    for i, line in enumerate(HOW_TO, start=1):
        how.cell(row=i, column=1, value=line).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    how.column_dimensions["A"].width = 100
    how["A19"], how["A20"] = "Stages in this file (do not edit):", ", ".join(s.stage for s in sections)
    how["A19"].font = how["A20"].font = Font(color="808080")

    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    list_ranges: Dict[tuple, str] = {}

    def list_range(options: List[str]) -> str:
        key = tuple(options)
        if key not in list_ranges:
            col = get_column_letter(len(list_ranges) + 1)
            for r, opt in enumerate(options, start=1):
                lists[f"{col}{r}"] = opt
            list_ranges[key] = f"Lists!${col}$1:${col}${len(options)}"
        return list_ranges[key]

    # Students sheet: every stage together
    ws = wb.create_sheet("Students")
    cols = [("Student ID", ID_KEY), ("Student Name", NAME_KEY), ("Stage", STAGE_KEY), ("Admission No", "admission_number"),
            ("Grade", "grade"), ("Section", "section"), ("Portal status", "status"), ("Sync (Yes/No)", SYNC_KEY)]
    _header(ws, cols)
    r = 3
    for section in sections:
        for s in section.students:
            values = {**s, STAGE_KEY: section.stage, SYNC_KEY: "No" if s.get("status") == "COMPLETED" else "Yes"}
            for c, (_, key) in enumerate(cols, start=1):
                ws.cell(row=r, column=c, value=values.get(key, ""))
            r += 1
    dv = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(f"H3:H{max(r - 1, 3)}")
    _finish_sheet(ws, [12, 28, 13, 14, 13, 9, 15, 13])

    # One sheet per stage and part
    for section in sections:
        for part in get_stage(section.stage).PARTS:
            title = f"{SHEET_PREFIX[section.stage]} {'Credit' if part.code == 'D' else part.code}"
            ws = wb.create_sheet(title)
            fields = part.fields(section.lookups)
            lead = [("Student ID", ID_KEY), ("Student Name", NAME_KEY)]
            if part.code == "B":
                lead.append((SUMMARY_HEADER, None))     # no key in row 2, so it is never read back
            first = len(lead) + 1
            _header(ws, lead + [(f.label, f.key) for f in fields])
            for c, f in enumerate(fields, start=first):
                head = ws.cell(row=1, column=c)
                if f.required:
                    head.fill = REQUIRED_FILL
                if f.kind in ("multi", "flags"):
                    head.comment = Comment("Choose from: " + ", ".join(f.options), "HPC")
                elif f.max_len:
                    head.comment = Comment(f"Up to {f.max_len} characters", "HPC")
            for r, s in enumerate(section.students, start=3):
                ws.cell(row=r, column=1, value=s[ID_KEY])
                ws.cell(row=r, column=2, value=s[NAME_KEY])
                values = section.rows.get(str(s[ID_KEY]), {})
                for c, f in enumerate(fields, start=first):
                    ws.cell(row=r, column=c, value=values.get(f.key, ""))
            last_row = max(len(section.students) + 2, 3)
            if part.code == "B":
                _summary_column(ws, section, last_row)
            for c, f in enumerate(fields, start=first):
                if f.kind in ("choice", "onehot", "inlist") and f.options:
                    v = DataValidation(type="list", formula1=f"={list_range(list(f.options))}", allow_blank=True)
                    ws.add_data_validation(v)
                    v.add(f"{get_column_letter(c)}3:{get_column_letter(c)}{last_row}")
            _finish_sheet(ws, [12, 28] + ([60] if part.code == "B" else []) +
                          [max(14, min(45, len(f.label) + 2)) for f in fields])

    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def read(path: Path, exception_problems: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """student_id -> {field key: cell value, 'stage': ..., 'sync': bool, 'student_name': ...}.
    Reads every workbook this app made: the per-part sheets (keys in row 2) and the class template
    (keys in row 3, plus its Exceptions sheet). Locked sheets (Part B, Settings, summary) are never read."""
    from backend.hpc import template
    wb = load_workbook(path, data_only=True)
    out: Dict[str, Dict[str, Any]] = {}
    for ws in wb.worksheets:
        if ws.title in template.LOCKED_SHEETS or ws.max_row < 2:
            continue
        key_row = next((r for r in (2, 3) if ID_KEY in [c.value for c in ws[r]]), None)
        if key_row is None:
            continue
        keys = [c.value for c in ws[key_row]]
        id_col = keys.index(ID_KEY)
        for row in ws.iter_rows(min_row=key_row + 1, values_only=True):
            sid = row[id_col]
            if sid in (None, ""):
                continue
            entry = out.setdefault(str(sid).split(".")[0].strip(), {})
            for key, value in zip(keys, row):
                if key and key != ID_KEY:
                    entry[key] = value
    meta = template.info(wb)
    if meta["is_template"] and meta.get("stage"):
        exceptions, problems = template.read_exceptions(wb, meta["stage"], set(out))
        for sid, values in exceptions.items():
            out[sid].update(values)
        if exception_problems is not None:
            exception_problems.extend(problems)
    for entry in out.values():
        entry[SYNC_KEY] = str(entry.get(SYNC_KEY, "Yes")).strip().lower() in ("yes", "y", "true", "1")
    return out


def template_info(path: Path) -> Dict[str, Any]:
    from backend.hpc import template
    wb = load_workbook(path, read_only=False, data_only=True)
    return template.info(wb)


def detect_stages(path: Path) -> List[str]:
    """Stages listed in the How-to sheet (empty if this isn't a workbook from this app)."""
    wb = load_workbook(path, read_only=True)
    try:
        text = str(wb["How to use"]["A20"].value or "")
    except KeyError:
        return []
    finally:
        wb.close()                    # read-only mode keeps the file open (and locked on Windows) until closed
    return [s.strip() for s in text.split(",") if s.strip() in SHEET_PREFIX]


def _summary_column(ws, section: Section, last_row: int) -> None:
    """Column C of a Part B sheet: what the Activities tab has chosen. Typing in it is refused."""
    for r in range(3, last_row + 1):
        sid = str(ws.cell(row=r, column=1).value or "")
        cell = ws.cell(row=r, column=3, value=section.activity_summaries.get(sid, ""))
        cell.fill = SUMMARY_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=1, column=3).comment = Comment("Choose activities and levels on the web app's Activities tab.", "HPC")
    dv = DataValidation(type="custom", formula1="FALSE", allow_blank=False, showErrorMessage=True,
                        errorTitle="Set on the Activities tab",
                        error="Activities and levels are chosen on the web app's Activities tab. This column only shows them.")
    ws.add_data_validation(dv)
    dv.add(f"C3:C{max(last_row, 500)}")


def set_activity_summaries(path: Path, summaries: Dict[str, Dict[str, str]]) -> None:
    """Refreshes the read-only Part B summary column: {stage: {student_id: text}}."""
    wb = load_workbook(path)
    for stage, by_student in summaries.items():
        title = f"{SHEET_PREFIX.get(stage, stage)} B"
        if title not in wb.sheetnames:
            continue
        ws = wb[title]
        if ws.cell(row=1, column=3).value != SUMMARY_HEADER:
            continue                                   # a file from before the Activities tab
        for r in range(3, ws.max_row + 1):
            sid = str(ws.cell(row=r, column=1).value or "").split(".")[0]
            if sid in by_student:
                ws.cell(row=r, column=3, value=by_student[sid])
    wb.save(path)


def _header(ws, cols):
    for c, (label, key) in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(row=2, column=c, value=key)
    ws.row_dimensions[1].height = 45
    ws.row_dimensions[2].hidden = True


def _finish_sheet(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "C3"
