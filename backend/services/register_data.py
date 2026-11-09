"""
School Register, phase 2 (docs/school_register_plan.md): what the school sets and enters once for every student.

settings   per stage and session: working days per month (April..March) and summative max marks per subject.
           Teachers read them. Every save is a new version (the older ones are kept).
workbook   "School Data" Excel: an Instructions sheet, one sheet per stage with every register student - their PARAKH
           identity (locked), father's name (from UDISE+ where a student matches, else what was entered),
           whose name the HPC card shows, days present per month (absent and % worked out), marks obtained. A hidden
           sheet names the template, school and session.
check      an uploaded workbook (nothing saved yet): every row matched to its register student by the register id and
           the PARAKH id, identity edits flagged for review, days present against the month's working days, marks
           against the max, names, duplicates, students left out. Kept as an import (the preview).
apply      saves the checked import's ready rows; rows unchanged since the last import change nothing.
for_cards  (phase 3) the card values each student gets from the school: working days, days present, the guardian
           shown on the card, max and obtained marks.

Monthly totals only - no daily attendance. Only what PARAKH's card has: leave days and assessment periods are not here.
"""
import hashlib
import io
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.database import SessionLocal
from backend.hpc import credit
from backend.hpc.stages.common import MONTH_DAYS, MONTH_NAMES, MONTHS
from backend.models.register import (RegisterImport, RegisterSetting, RegisterSettingVersion, RegisterStudent,
                                     RegisterStudentData)

TEMPLATE = "school-data-v2"            # v2: no mother's name column (one name column for Mother / Guardian)
STAGES = ["Foundational", "Preparatory", "Middle"]
RELATIONS = ["Father", "Mother", "Guardian"]
NAME_MAX = 50                                         # PARAKH's limit for the parent/guardian name on the card
NAME_RULE = re.compile(r"^[A-Za-z][A-Za-z .'\-]*$")
IDENTITY = ["Register ID", "PARAKH ID", "Student name (PARAKH)", "Class", "Section", "APAAR ID", "Date of birth",
            "Admission no."]
PARENTS = ["Father's name", "Name on the HPC card", "Mother's or guardian's name (if chosen)"]


class Problem(ValueError):
    pass


# ---------------------------------------------------------------------------
# Session and settings
# ---------------------------------------------------------------------------

def session_of(school_id: str) -> str:
    """The academic year the school's PARAKH login is in (e.g. 2627); else the last one settings were saved for."""
    from backend.services import hpc_sessions
    sess = hpc_sessions.load_session("school", school_id)
    code = str((sess.staff if sess else {}).get("school_cur_ay_code") or "")
    if code:
        return code
    with SessionLocal() as db:
        last = db.query(RegisterSetting).filter_by(school_id=school_id).order_by(RegisterSetting.updated_at.desc()).first()
    if last:
        return last.session
    raise Problem("The academic year is not known yet: connect the school to PARAKH once.")


def subjects(stage: str) -> List[Tuple[str, str]]:
    """(n, subject) with summative marks on PARAKH's card ([] for Foundational)."""
    return credit.summative_subjects(stage.lower())


DEFAULT_MAX_MARKS = 50                           # summative max marks of every subject until the school sets its own


def blank(stage: str) -> Dict[str, Any]:
    return {"working_days": [None] * 12, "max_marks": {n: DEFAULT_MAX_MARKS for n, _ in subjects(stage)}}


def get_settings(school_id: str, stage: str, session: str) -> Dict[str, Any]:
    with SessionLocal() as db:
        row = db.query(RegisterSetting).filter_by(school_id=school_id, stage=stage, session=session).first()
        if row is None:
            return {"stage": stage, "session": session, "values": blank(stage), "version": 0, "updated_at": None,
                    "subjects": [{"n": n, "name": s} for n, s in subjects(stage)]}
        values = {**blank(stage), **(row.values or {})}
        values["max_marks"] = {n: (values.get("max_marks") or {}).get(n) or DEFAULT_MAX_MARKS for n, _ in subjects(stage)}
        return {"stage": stage, "session": session, "values": values, "version": row.version,
                "updated_at": row.updated_at.isoformat(timespec="seconds") + "Z" if row.updated_at else None,
                "subjects": [{"n": n, "name": s} for n, s in subjects(stage)]}


def last_change(school_id: str) -> Optional[datetime]:
    """When the School Register's values (settings, attendance, parents, marks) last changed (UTC), or None."""
    from sqlalchemy import func
    with SessionLocal() as db:
        a = db.query(func.max(RegisterStudentData.updated_at)).filter_by(school_id=school_id).scalar()
        b = db.query(func.max(RegisterSetting.updated_at)).filter_by(school_id=school_id).scalar()
    return max([t for t in (a, b) if t is not None], default=None)


def _whole(value: Any) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    number = float(str(value).strip())
    if not number.is_integer():
        raise ValueError
    return int(number)


def validate_settings(stage: str, values: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    clean, problems = blank(stage), {}
    days = (list(values.get("working_days") or []) + [None] * 12)[:12]
    for i, (month, d) in enumerate(zip(MONTHS, days)):
        try:
            n = _whole(d)
        except ValueError:
            problems[f"working_days.{i}"] = f"{MONTH_NAMES[month]}: a whole number"
            continue
        if n is not None and not 0 <= n <= MONTH_DAYS[month]:
            problems[f"working_days.{i}"] = f"{MONTH_NAMES[month]}: between 0 and {MONTH_DAYS[month]}"
            continue
        clean["working_days"][i] = n
    given = values.get("max_marks") or {}
    for n, name in subjects(stage):
        try:
            m = _whole(given.get(n))
        except ValueError:
            problems[f"max_marks.{n}"] = f"{name}: a whole number"
            continue
        if m is not None and m <= 0:
            problems[f"max_marks.{n}"] = f"{name}: more than 0"
            continue
        clean["max_marks"][n] = m
    return clean, problems


def save_settings(school_id: str, stage: str, session: str, values: Dict[str, Any], by: str) -> Dict[str, Any]:
    clean, problems = validate_settings(stage, values)
    if problems:
        raise Problem(json.dumps(problems))
    with SessionLocal() as db:
        row = db.query(RegisterSetting).filter_by(school_id=school_id, stage=stage, session=session).first()
        if row is None:
            row = RegisterSetting(school_id=school_id, stage=stage, session=session, values=clean, version=1, updated_by=by)
            db.add(row)
            db.flush()
        elif row.values == clean:
            return get_settings(school_id, stage, session)
        else:
            row.values, row.version, row.updated_by = clean, row.version + 1, by
        db.add(RegisterSettingVersion(setting_id=row.id, version=row.version, values=clean, saved_by=by))
        db.commit()
    return get_settings(school_id, stage, session)


# ---------------------------------------------------------------------------
# Parentage from UDISE+ (SDMS, as last fetched)
# ---------------------------------------------------------------------------

def _letters(text: Any) -> str:
    return re.sub(r"[^A-Z]", "", str(text or "").upper())


def _adm(text: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper()).lstrip("0")


def _dob(text: Any) -> str:
    t = str(text or "").strip()[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else t


PARENTS_FILE = "udise_parents.json"


def _parents_path(school_id: str):
    from backend.services.hpc_sessions import session_dir
    return session_dir("school", school_id) / PARENTS_FILE


def fetch_parents(school_id: str) -> Dict[str, Any]:
    """Reads UDISE+ (SDMS) again for the parents' names - one request: every student's basic details, students added
    since the last full SDMS fetch included. Kept apart from the full SDMS copy (which other pages use)."""
    from backend.services import secrets_box, udise_sessions
    from backend.udise.client import UdiseError
    from backend.udise.sdms import Sdms, SessionEnded
    saved = udise_sessions._load(school_id)
    if not (saved.get("services", {}).get("sdms") or {}).get("connected"):
        raise Problem("UDISE+ (SDMS) is not connected: press 'Connect UDISE+' on the Home page, then try again.")
    try:
        sdms = Sdms(saved)
        rows = sdms.students(sdms.school_id())
    except SessionEnded as exc:
        raise Problem(str(exc))
    except UdiseError as exc:
        raise Problem(f"UDISE+ did not answer: {exc}")
    keep = ("studentId", "studentName", "fatherName", "motherName", "dob", "classDesc", "sectionDesc", "apaarId")
    body = {"fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "students": [{k: r.get(k) for k in keep} for r in rows if isinstance(r, dict)]}
    path = _parents_path(school_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(body, ensure_ascii=False)), encoding="utf-8")
    tmp.replace(path)
    return {"fetched_at": body["fetched_at"], "students": len(body["students"])}


def _fresh_parents(school_id: str) -> Optional[Dict[str, Any]]:
    from backend.services import secrets_box
    path = _parents_path(school_id)
    if not path.exists():
        return None
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _sdms_rows(school_id: str) -> Tuple[List[Tuple[Dict, Dict, Dict]], Optional[str], str]:
    """(SDMS students as (general, enrolment, apaar), when read, "full" | "quick") - the newer of the full SDMS
    fetch and the quick parents read; a quick read keeps the full fetch's admission numbers and APAAR IDs."""
    from backend.services.sdms_data import load as load_sdms
    full = load_sdms(school_id) or {}
    quick = _fresh_parents(school_id)
    if quick and quick.get("fetched_at", "") > (full.get("fetched_at") or ""):
        old = {s["general"].get("studentId"): s for s in full.get("students", [])}
        rows = []
        for g in quick["students"]:
            before = old.get(g.get("studentId")) or {}
            rows.append(({**(before.get("general") or {}), **g}, before.get("enrolment") or {}, before.get("apaar") or {}))
        return rows, quick["fetched_at"], "quick"
    return ([(s["general"], s.get("enrolment") or {}, s.get("apaar") or {}) for s in full.get("students", [])],
            full.get("fetched_at"), "full")


def parents_source(school_id: str) -> Dict[str, Any]:
    rows, when, kind = _sdms_rows(school_id)
    return {"fetched_at": when, "kind": kind if rows else None, "students": len(rows)}


def udise_parents(school_id: str, students: List[RegisterStudent]) -> Dict[str, Dict[str, str]]:
    """register id -> {"father", "mother"} from UDISE+ for the students that match one SDMS student - by APAAR ID,
    else admission number, else name and date of birth (a key two students share matches nobody)."""
    sdms, _, _ = _sdms_rows(school_id)
    if not sdms:
        return {}
    keys = [("apaar", lambda g, e, a: next((str(v) for v in (a.get("apaarId"), g.get("apaarId")) if v not in (None, "", "NA")), ""),
             lambda r: r.apaar_id or ""),
            ("adm", lambda g, e, a: _adm(e.get("admnNumber") or g.get("admnNumber")), lambda r: _adm(r.admission_number)),
            ("namedob", lambda g, e, a: _letters(g.get("studentName")) + "|" + _dob(g.get("dob")) if g.get("dob") else "",
             lambda r: _letters(r.student_name) + "|" + _dob(r.dob) if r.dob else "")]
    out: Dict[str, Dict[str, str]] = {}
    free = set(range(len(sdms)))
    for _, of_sdms, of_reg in keys:
        index: Dict[str, List[int]] = {}
        for i in free:
            k = of_sdms(*sdms[i])
            if k and k != "|":
                index.setdefault(k, []).append(i)
        for r in students:
            if r.id in out:
                continue
            k = of_reg(r)
            hits = [i for i in index.get(k, []) if i in free] if k else []
            if len(hits) == 1:
                g = sdms[hits[0]][0]
                free.discard(hits[0])
                out[r.id] = {"father": str(g.get("fatherName") or "").strip(), "mother": str(g.get("motherName") or "").strip()}
    return out


# ---------------------------------------------------------------------------
# The workbook
# ---------------------------------------------------------------------------

def _columns(stage: str, settings: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(group, title) for every column of a stage sheet, in order."""
    days = settings["values"]["working_days"]
    cols = [("Student (from PARAKH - do not change)", t) for t in IDENTITY]
    cols += [("Parents", t) for t in PARENTS]
    cols += [("Days present (working days in brackets)", f"{m} present ({'?' if d is None else d})") for m, d in zip(MONTHS, days)]
    cols += [("Attendance (worked out)", t) for t in ("Days present", "Working days", "Days absent", "Attendance %")]
    cols += [("Summative marks obtained (max in brackets)",
              f"{name} ({'?' if settings['values']['max_marks'].get(n) is None else settings['values']['max_marks'][n]})")
             for n, name in subjects(stage)]
    return cols


def workbook(school_id: str) -> Tuple[bytes, str]:
    """(xlsx bytes, file name)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter, quote_sheetname
    from openpyxl.worksheet.datavalidation import DataValidation
    from backend.hpc.xl import formula, grid, keep_text
    session = session_of(school_id)
    with SessionLocal() as db:
        students = db.query(RegisterStudent).filter(RegisterStudent.school_id == school_id,
                                                   RegisterStudent.missing_since.is_(None)).all()
        if not students:
            raise Problem("The register is empty: fetch the students from PARAKH first.")
        stored = {d.student_id: d for d in db.query(RegisterStudentData).filter_by(school_id=school_id, session=session)}
        parents = udise_parents(school_id, students)
        parents_when = (parents_source(school_id)["fetched_at"] or "")[:16].replace("T", " ")
    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    lines = [f"School Data, academic year {session[:2]}-{session[2:]} (template {TEMPLATE})", "",
             "1. One sheet per stage, one row per student as PARAKH lists them. Do not change the grey columns: "
             "the PARAKH ID and name identify the student.",
             f"2. Parents: the father's name (filled from UDISE+ as read on {parents_when or 'never'}, where "
             "the student was found there). "
             "'Name on the HPC card' says whose name PARAKH's card shows (empty: the father); for Mother or Guardian "
             "write that name in the next column.",
             "3. Days present per month: a whole number, at most the month's working days (in the column heading, "
             "set by the school in the app). Leave a month empty when there is no data - it is never taken as 0.",
             "4. Marks obtained: at most the subject's max marks (in the heading). Leave empty when not yet known.",
             "5. Upload the file on the School Register page: it is checked first and nothing is saved until you "
             "press Save. Uploading the same file again changes nothing.",
             "Monthly totals only - there is no daily attendance."]
    for i, line in enumerate(lines, start=1):
        info.cell(row=i, column=1, value=line).alignment = Alignment(wrap_text=True)
    info["A1"].font = Font(bold=True, size=13)
    info.column_dimensions["A"].width = 120
    lists = wb.create_sheet("Lists")
    for i, rel in enumerate(RELATIONS, start=1):
        lists.cell(row=i, column=1, value=rel)
    lists.sheet_state = "hidden"
    meta = wb.create_sheet("_meta")
    meta.sheet_state = "hidden"
    grey = PatternFill("solid", fgColor="E2E8F0")
    head = PatternFill("solid", fgColor="0B5FA5")
    entry = PatternFill("solid", fgColor="FFFBEB")
    white = Font(bold=True, color="FFFFFF")
    snapshot = {}
    by_stage: Dict[str, List[RegisterStudent]] = {}
    for s in students:
        by_stage.setdefault(s.stage, []).append(s)
    for stage in [s for s in STAGES if s in by_stage]:
        settings = get_settings(school_id, stage, session)
        snapshot[stage] = settings["values"]
        cols = _columns(stage, settings)
        ws = wb.create_sheet(stage)
        group_start = 1
        for c, (group, title) in enumerate(cols, start=1):
            if c == len(cols) or cols[c][0] != group:
                ws.cell(row=1, column=group_start, value=group).font = white
                for k in range(group_start, c + 1):
                    ws.cell(row=1, column=k).fill = head
                if c > group_start:
                    ws.merge_cells(start_row=1, start_column=group_start, end_row=1, end_column=c)
                group_start = c + 1
            cell = ws.cell(row=2, column=c, value=title)
            cell.font, cell.fill = Font(bold=True), grey
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        rows = sorted(by_stage[stage], key=lambda s: (s.grade_id or 0, str(s.section or ""), s.student_name))
        first_month = len(IDENTITY) + len(PARENTS) + 1
        total_col = first_month + 12
        days = settings["values"]["working_days"]
        for r, s in enumerate(rows, start=3):
            d = stored.get(s.id)
            udise = parents.get(s.id, {})
            values = [s.id, s.parakh_student_id, s.student_name, s.grade, s.section, s.apaar_id, s.dob, s.admission_number,
                      (d.father_name if d and d.father_name else udise.get("father")) or None,
                      (d.guardian_relation if d else None) or None,
                      ({"Mother": d.mother_name, "Guardian": d.guardian_name}.get(d.guardian_relation or "") if d else None) or None]
            present = list((d.present if d else None) or []) + [None] * 12
            values += present[:12]
            for c, v in enumerate(values, start=1):
                cell = ws.cell(row=r, column=c, value=v)
                if c > len(IDENTITY):
                    cell.protection = Protection(locked=False)
                    cell.fill = entry
                if len(IDENTITY) < c <= len(IDENTITY) + len(PARENTS):
                    cell.number_format = "@"
            p = f"{get_column_letter(first_month)}{r}:{get_column_letter(first_month + 11)}{r}"
            worked = "+".join(f"IF({get_column_letter(first_month + i)}{r}=\"\",0,{d})" for i, d in enumerate(days) if d is not None) or "0"
            formula(ws, r, total_col, f"=SUM({p})")
            formula(ws, r, total_col + 1, f"={worked}")
            formula(ws, r, total_col + 2, f"=MAX({get_column_letter(total_col + 1)}{r}-{get_column_letter(total_col)}{r},0)")
            formula(ws, r, total_col + 3, f"=IF({get_column_letter(total_col + 1)}{r}=0,\"\",ROUND({get_column_letter(total_col)}{r}"
                                          f"/{get_column_letter(total_col + 1)}{r}*100,2))")
            marks = (d.marks if d else None) or {}
            for k, (n, _) in enumerate(subjects(stage)):
                cell = ws.cell(row=r, column=total_col + 4 + k, value=marks.get(n))
                cell.protection, cell.fill = Protection(locked=False), entry
        last = len(rows) + 2
        rel_col = get_column_letter(len(IDENTITY) + 2)
        dv = DataValidation(type="list", formula1=f"{quote_sheetname('Lists')}!$A$1:$A$3", allow_blank=True,
                            showErrorMessage=True, errorTitle="Choose from the list", error="Father, Mother or Guardian")
        dv.add(f"{rel_col}3:{rel_col}{last}")
        ws.add_data_validation(dv)
        for i, d in enumerate(days):
            col = get_column_letter(first_month + i)
            dv = DataValidation(type="whole", operator="between", formula1="0", formula2=str(d if d is not None else 31),
                                allow_blank=True, showErrorMessage=True, errorTitle="Days present",
                                error=f"A whole number from 0 to {d if d is not None else 31}")
            dv.add(f"{col}3:{col}{last}")
            ws.add_data_validation(dv)
        grid(ws, 1, last, 1, len(cols))                  # headings and every student cell, fill-in columns too
        ws.column_dimensions["A"].hidden = True
        for c, (_, title) in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(c)].width = 30 if title.startswith(("Student name", "Father", "Mother", "Guardian")) \
                else 12 if " present (" in title else 16
        ws.row_dimensions[2].height = 45
        ws.freeze_panes = "D3"
        ws.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{last}"
        ws.protection.sheet = True
        ws.protection.formatColumns = ws.protection.autoFilter = ws.protection.sort = False
    for i, (k, v) in enumerate((("template", TEMPLATE), ("school_id", school_id), ("session", session),
                                ("generated_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
                                ("settings", json.dumps(snapshot))), start=1):
        meta.cell(row=i, column=1, value=k)
        meta.cell(row=i, column=2, value=v)
    keep_text(wb)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), f"School_Data_{session}.xlsx"


# ---------------------------------------------------------------------------
# Check (preview) and apply
# ---------------------------------------------------------------------------

def _bare(title: str) -> str:
    """A column heading without its trailing "(…)" (working days or max marks, which the school may change)."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", _text(title))


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def _name(v: Any, label: str, problems: List[str]) -> Optional[str]:
    t = _text(v)
    if not t:
        return None
    if len(t) > NAME_MAX or not NAME_RULE.match(t):
        problems.append(f"{label}: letters, spaces, . ' - only (up to {NAME_MAX})")
        return None
    return t


def check(school_id: str, content: bytes, file_name: str, by: str) -> Dict[str, Any]:
    from openpyxl import load_workbook
    from backend.hpc.xl import unpacked_size_ok
    if not unpacked_size_ok(content):
        raise Problem("This is not an Excel file the app can read (.xlsx), or it is damaged.")
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise Problem("This is not an Excel file the app can read (.xlsx).")
    if "_meta" not in wb.sheetnames:
        raise Problem("This is not the School Data workbook: download it from the School Register page and fill that.")
    meta = {str(r[0].value): r[1].value for r in wb["_meta"].iter_rows(max_col=2) if r[0].value}
    if meta.get("template") != TEMPLATE:
        raise Problem(f"This workbook is an older or other template ({meta.get('template')}): download a new one.")
    if meta.get("school_id") != school_id:
        raise Problem("This workbook belongs to another school.")
    session = session_of(school_id)
    if str(meta.get("session")) != session:
        raise Problem(f"This workbook is for academic year {meta.get('session')}, not the current {session}.")
    digest = hashlib.sha256(content).hexdigest()
    with SessionLocal() as db:
        register = {s.id: s for s in db.query(RegisterStudent).filter_by(school_id=school_id)}
        by_parakh = {(s.stage, s.parakh_student_id): s for s in register.values()}
        stored = {d.student_id: d for d in db.query(RegisterStudentData).filter_by(school_id=school_id, session=session)}
        applied = db.query(RegisterImport).filter_by(school_id=school_id, file_hash=digest, status="APPLIED").first()
    rows_out, seen = [], {}
    counts = {"ready": 0, "unchanged": 0, "problem": 0, "review": 0}
    listed: Dict[str, set] = {}
    for stage in [s for s in STAGES if s in wb.sheetnames]:
        ws = wb[stage]
        settings = get_settings(school_id, stage, session)["values"]
        heads = [_text(c.value) for c in ws[2]]
        if heads[:len(IDENTITY)] != IDENTITY:
            raise Problem(f"Sheet '{stage}': its columns were changed - download a new workbook.")
        # Every column is read by its place: a deleted or moved column would shift the rest (marks read as days
        # present). The headings must match the template's (the numbers in brackets may differ: settings change).
        expected = [_bare(t) for _, t in _columns(stage, {"values": settings})]
        got = [_bare(h) for h in heads[:len(expected)]] + [""] * max(0, len(expected) - len(heads))
        if got != expected:
            gone = [t for t in expected if t not in got]
            raise Problem(f"Sheet '{stage}': columns were deleted or moved"
                          + (f" (missing: {', '.join(gone[:6])}{'…' if len(gone) > 6 else ''})" if gone else "")
                          + ". Every column must stay where the app put it: download a new workbook and fill that.")
        subs = subjects(stage)
        first_month = len(IDENTITY) + len(PARENTS)
        marks_at = first_month + 12 + 4
        for r, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            row = list(row) + [None] * (marks_at + len(subs))
            reg_id, pid, name = _text(row[0]), _text(row[1]), _text(row[2])
            if not reg_id and not pid and not name:
                continue
            where = {"sheet": stage, "row": r, "parakh_id": pid, "name": name}
            student = register.get(reg_id) or by_parakh.get((stage, pid))
            if student is None or student.stage != stage:
                rows_out.append({**where, "outcome": "review", "problems": ["Not a student of this school's register "
                                 "(PARAKH ID or hidden register ID changed or unknown)"], "changes": []})
                counts["review"] += 1
                continue
            listed.setdefault(stage, set()).add(student.id)
            edited = [label for label, now, before in (("PARAKH ID", pid, student.parakh_student_id),
                                                       ("student name", name, student.student_name))
                      if now != _text(before)]
            if edited or (reg_id and reg_id != student.id):
                rows_out.append({**where, "outcome": "review", "student_id": student.id,
                                 "problems": [f"The {', '.join(edited) or 'register ID'} was changed in the file - "
                                              "identity comes from PARAKH; fix the row (nothing from it is saved)"],
                                 "changes": []})
                counts["review"] += 1
                continue
            if student.id in seen:
                rows_out.append({**where, "outcome": "problem", "student_id": student.id,
                                 "problems": [f"The same student is also on row {seen[student.id]}"], "changes": []})
                counts["problem"] += 1
                continue
            seen[student.id] = r
            problems: List[str] = []
            father = _name(row[8], "Father's name", problems)
            relation = _text(row[9]).title() or None
            if relation and relation not in RELATIONS:
                problems.append("Name on the HPC card: Father, Mother or Guardian")
                relation = None
            other = _name(row[10], "Mother's or guardian's name", problems)
            if relation in ("Mother", "Guardian") and not other:
                problems.append(f"Name on the HPC card is {relation}: write the {relation.lower()}'s name")
            if relation == "Father" and not father:
                problems.append("Name on the HPC card is Father: write the father's name")
            present: List[Optional[int]] = []
            for i, month in enumerate(MONTHS):
                v = row[first_month + i]
                try:
                    n = _whole(v)
                except ValueError:
                    problems.append(f"{MONTH_NAMES[month]}: days present must be a whole number")
                    present.append(None)
                    continue
                days = settings["working_days"][i]
                if n is not None and days is None:
                    problems.append(f"{MONTH_NAMES[month]}: the school has not set its working days yet")
                elif n is not None and not 0 <= n <= days:
                    problems.append(f"{MONTH_NAMES[month]}: {n} days present, but {days} working days")
                present.append(n)
            marks: Dict[str, Optional[float]] = {}
            for k, (n, sub) in enumerate(subs):
                v = row[marks_at + k]
                if v is None or _text(v) == "":
                    marks[n] = None
                    continue
                try:
                    m = float(_text(v))
                except ValueError:
                    problems.append(f"{sub}: marks must be a number")
                    continue
                mx = settings["max_marks"].get(n)
                if mx is None:
                    problems.append(f"{sub}: the school has not set the max marks yet")
                elif not 0 <= m <= mx:
                    problems.append(f"{sub}: {m:g} marks, but the max is {mx}")
                marks[n] = int(m) if m.is_integer() else m
            new = {"father_name": father, "guardian_relation": relation,
                   "guardian_name": other if relation == "Guardian" else None, "present": present, "marks": marks}
            if relation == "Mother":                       # the mother's name only when the card shows it
                new["mother_name"] = other
            old = stored.get(student.id)
            before = {"father_name": old.father_name if old else None, "mother_name": old.mother_name if old else None,
                      "guardian_relation": old.guardian_relation if old else None,
                      "guardian_name": old.guardian_name if old else None,
                      "present": (list(old.present or []) + [None] * 12)[:12] if old else [None] * 12,
                      "marks": {n: (old.marks or {}).get(n) for n, _ in subs} if old else {n: None for n, _ in subs}}
            changes = [k for k in new if new[k] != before[k]]
            outcome = "problem" if problems else ("ready" if changes else "unchanged")
            counts[outcome] += 1
            rows_out.append({**where, "outcome": outcome, "student_id": student.id, "problems": problems,
                             "changes": changes, "values": new if outcome == "ready" else None})
    missing = {st: sum(1 for s in register.values() if s.stage == st and s.missing_since is None
                       and s.id not in listed.get(st, set())) for st in STAGES}
    summary = {**counts, "left_out": {k: v for k, v in missing.items() if v},
               "already_applied_at": applied.applied_at.isoformat(timespec="seconds") + "Z" if applied and applied.applied_at else None}
    with SessionLocal() as db:
        db.query(RegisterImport).filter_by(school_id=school_id, status="CHECKED").update({"status": "SUPERSEDED"})
        imp = RegisterImport(school_id=school_id, session=session, file_name=file_name[:255], file_hash=digest,
                             status="CHECKED", summary=summary, rows=rows_out, created_by=by)
        db.add(imp)
        db.commit()
        return _public(imp)


def _public(imp: RegisterImport) -> Dict[str, Any]:
    rows = [{k: v for k, v in r.items() if k != "values"} for r in (imp.rows or [])]
    return {"id": imp.id, "file_name": imp.file_name, "status": imp.status, "session": imp.session,
            "summary": imp.summary, "rows": [r for r in rows if r["outcome"] != "unchanged"],
            "created_at": imp.created_at.isoformat(timespec="seconds") + "Z" if imp.created_at else None,
            "applied_at": imp.applied_at.isoformat(timespec="seconds") + "Z" if imp.applied_at else None}


def apply(school_id: str, import_id: str, by: str) -> Dict[str, Any]:
    from backend.services import audit
    with SessionLocal() as db:
        imp = db.query(RegisterImport).filter_by(id=import_id, school_id=school_id).first()
        if imp is None or imp.status != "CHECKED":
            raise Problem("Upload and check the workbook again: this check is not the latest one.")
        saved = 0
        for r in imp.rows or []:
            if r["outcome"] != "ready" or not r.get("values"):
                continue
            student = db.get(RegisterStudent, r["student_id"])
            if student is None or student.school_id != school_id:
                continue
            d = db.query(RegisterStudentData).filter_by(student_id=student.id, session=imp.session).first()
            if d is None:
                d = RegisterStudentData(school_id=school_id, student_id=student.id, session=imp.session, sources={})
                db.add(d)
            sources = dict(d.sources or {})
            for k in r["changes"]:
                setattr(d, k, r["values"][k])
                sources[k] = f"import:{imp.id}"
            d.sources, d.import_id = sources, imp.id
            saved += 1
        imp.status, imp.applied_at = "APPLIED", datetime.utcnow()
        db.commit()
        result = _public(imp)
    audit.record(f"school_admin:{school_id}", "register_import", "register", import_id, None,
                 {"saved": saved, "summary": result["summary"]})
    return {**result, "saved": saved}


def history(school_id: str) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.query(RegisterImport).filter_by(school_id=school_id).order_by(RegisterImport.created_at.desc()).limit(20).all()
        return [{"id": i.id, "file_name": i.file_name, "status": i.status, "summary": i.summary,
                 "created_at": i.created_at.isoformat(timespec="seconds") + "Z" if i.created_at else None,
                 "applied_at": i.applied_at.isoformat(timespec="seconds") + "Z" if i.applied_at else None} for i in rows]


def latest_check(school_id: str) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        imp = db.query(RegisterImport).filter_by(school_id=school_id).order_by(RegisterImport.created_at.desc()).first()
        return _public(imp) if imp else None


# ---------------------------------------------------------------------------
# What the school has entered (dashboard) and what goes on the cards (phase 3)
# ---------------------------------------------------------------------------

def entered(school_id: str, session: str) -> Dict[str, Dict[str, Any]]:
    """register id -> a short summary: days present / working days / %, parents, marks filled."""
    out = {}
    with SessionLocal() as db:
        students = {s.id: s for s in db.query(RegisterStudent).filter_by(school_id=school_id)}
        settings = {st: get_settings(school_id, st, session)["values"] for st in STAGES}
        for d in db.query(RegisterStudentData).filter_by(school_id=school_id, session=session):
            s = students.get(d.student_id)
            if s is None:
                continue
            days = settings[s.stage]["working_days"]
            present = (list(d.present or []) + [None] * 12)[:12]
            got = sum(p for p in present if p is not None)
            worked = sum(w for p, w in zip(present, days) if p is not None and w is not None)
            marks = {k: v for k, v in (d.marks or {}).items() if v is not None}
            out[d.student_id] = {"present": got, "working": worked, "percent": round(got / worked * 100, 2) if worked else None,
                                 "months": sum(1 for p in present if p is not None), "father": d.father_name,
                                 "mother": d.mother_name, "card_name": d.guardian_relation,
                                 "marks": len(marks), "marks_of": len(subjects(s.stage))}
    return out


def for_cards(school_id: str, stage: str, session: str, parakh_student_id: str) -> Dict[str, Any]:
    """The card values (workbook keys) the school gives one student: working days and max marks from the settings,
    days present, the parent/guardian shown on the card, marks obtained. {} keys are left out when not entered."""
    settings = get_settings(school_id, stage, session)["values"]
    out: Dict[str, Any] = {}
    for i, d in enumerate(settings["working_days"]):
        if d is not None:
            out[f"a1_working_{i + 1}"] = d
    for n, _ in subjects(stage):
        if settings["max_marks"].get(n) is not None:
            out[f"d_{n}_max"] = settings["max_marks"][n]
    with SessionLocal() as db:
        s = db.query(RegisterStudent).filter_by(school_id=school_id, stage=stage, parakh_student_id=str(parakh_student_id)).first()
        d = db.query(RegisterStudentData).filter_by(student_id=s.id, session=session).first() if s else None
    if d is None:
        return out
    for i, p in enumerate((list(d.present or []) + [None] * 12)[:12]):
        if p is not None:
            out[f"a1_present_{i + 1}"] = p
    for n, m in (d.marks or {}).items():
        if m is not None:
            out[f"d_{n}_obtained"] = m
    relation = d.guardian_relation or ("Father" if d.father_name else None)      # PARAKH's page pre-selects Father
    name = {"Father": d.father_name, "Mother": d.mother_name, "Guardian": d.guardian_name}.get(relation or "")
    if relation and name:
        out["a1_guardian_relation"], out["a1_guardian_name"] = relation, name
    return out


def card_values(stage: str, record: Dict[str, Any], student_id: str) -> Dict[str, Any]:
    """common.SCHOOL_VALUES: the school's values for a student's card, found from PARAKH's record (its school UDISE
    code and academic year). {} when the school has none."""
    from backend.hpc.portal import stage_code
    from backend.models.entities import School
    udise = str((record.get("sch_info") or {}).get("school_udise") or "").strip()
    session = str((record.get("stu_info") or {}).get("school_cur_ay_code") or record.get("school_cur_ay_code") or "").strip()
    if not udise or not session:
        return {}
    with SessionLocal() as db:
        school = db.query(School).filter_by(udise_code=udise).first()
    if school is None:
        return {}
    return for_cards(school.id, stage_code(stage).capitalize(), session, student_id)


from backend.hpc.stages import common as _common   # noqa: E402  (registered when this module is imported)
_common.SCHOOL_VALUES = card_values


# ---------------------------------------------------------------------------
# Levels from the summative marks (Global Mix): a student's marks in a subject decide that subject's levels
# ---------------------------------------------------------------------------

LEVEL_CUTS = ((75.0, "Advanced"), (50.0, "Proficient"), (0.0, "Beginner"))    # marks obtained / max, in %


def level_for(percent: float) -> str:
    return next(level for cut, level in LEVEL_CUTS if percent >= cut)


def levels_from_marks(school_id: str, stage: str, session: str, parakh_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """{PARAKH student id: {subject (domain) code: level}} from the marks the school entered. A subject with summative
    marks gets the level of its own %; a subject without (Other learning, Bagless days ...) the student's average %.
    Students without marks are left out (Global Mix deals their levels at random)."""
    from backend.hpc.stages import get_stage
    from backend.hpc.portal import stage_code
    title = stage_code(stage).capitalize()
    subs = subjects(title)
    if not subs:
        return {}
    domains = get_stage(stage_code(stage)).DOMAINS
    maxes = get_settings(school_id, title, session)["values"]["max_marks"]
    out: Dict[str, Dict[str, str]] = {}
    with SessionLocal() as db:
        rows = {s.parakh_student_id: s.id for s in db.query(RegisterStudent).filter(
            RegisterStudent.school_id == school_id, RegisterStudent.stage == title,
            RegisterStudent.parakh_student_id.in_([str(p) for p in parakh_ids]))}
        data = {d.student_id: d for d in db.query(RegisterStudentData).filter(
            RegisterStudentData.student_id.in_(list(rows.values())), RegisterStudentData.session == session)}
    for pid, rid in rows.items():
        d = data.get(rid)
        marks = (d.marks if d else None) or {}
        percents = {}
        for n, _ in subs:
            got, mx = marks.get(n), maxes.get(n)
            if got is not None and mx:
                percents[int(n) - 1] = float(got) / float(mx) * 100
        if not percents:
            continue
        average = sum(percents.values()) / len(percents)
        out[str(pid)] = {domain: level_for(percents.get(i, average)) for i, domain in enumerate(domains)}
    return out


# ---------------------------------------------------------------------------
# Dummy fill (the school's choice): attendance and marks at random inside a range, only where empty
# ---------------------------------------------------------------------------

def dummy_fill(school_id: str, attendance: Optional[Tuple[float, float]], marks: Optional[Tuple[int, int]],
               stage: Optional[str] = None, apply: bool = False, by: str = "", replace: bool = False) -> Dict[str, Any]:
    """attendance: (low %, high %) of each month's working days; marks: (low, high) marks obtained, never above the
    subject's max marks. Every student gets their own random value inside the range. Only EMPTY cells are filled:
    what was uploaded or entered stays - unless replace, which fills every cell again (and empties a month without
    working days, where days present cannot be). A month without working days stays empty. apply=False: counts only."""
    import math
    import random
    from backend.services import audit
    if attendance is None and marks is None:
        raise Problem("Choose attendance, marks or both.")
    if attendance is not None:
        lo, hi = attendance
        if not (0 <= lo <= hi <= 100):
            raise Problem("Attendance range: from 0 to 100 %, the first number not above the second.")
    if marks is not None:
        lo_m, hi_m = marks
        if not (0 <= lo_m <= hi_m):
            raise Problem("Marks range: 0 or more, the first number not above the second.")
    session = session_of(school_id)
    rng = random.Random()
    stamp = "dummy:" + datetime.utcnow().strftime("%Y-%m-%d")
    out: Dict[str, Any] = {"session": session, "stages": {}, "students": 0, "months": 0, "marks": 0, "notes": []}
    with SessionLocal() as db:
        q = db.query(RegisterStudent).filter(RegisterStudent.school_id == school_id, RegisterStudent.missing_since.is_(None))
        if stage:
            q = q.filter(RegisterStudent.stage == stage)
        students = q.all()
        if not students:
            raise Problem("The register is empty: fetch the students from PARAKH first.")
        stored = {d.student_id: d for d in db.query(RegisterStudentData).filter_by(school_id=school_id, session=session)}
        for st in [s for s in STAGES if any(x.stage == s for x in students)]:
            values = get_settings(school_id, st, session)["values"]
            days = values["working_days"]
            maxes = values["max_marks"]
            subs = [n for n, _ in subjects(st)]
            if attendance is not None and not any(d for d in days if d):
                out["notes"].append(f"{st}: no working days are set, so no attendance is filled. Set them in the "
                                    "settings above first.")
            counts = {"students": 0, "months": 0, "marks": 0}
            for s in [x for x in students if x.stage == st]:
                d = stored.get(s.id)
                present = list((d.present if d else None) or []) + [None] * 12
                present = present[:12]
                got = dict((d.marks if d else None) or {})
                months = filled = 0
                if attendance is not None:
                    for i, wd in enumerate(days):
                        if replace and not wd and present[i] not in (None, ""):
                            present[i] = None                 # no working days that month: no days present
                            months += 1
                            continue
                        if wd and (replace or present[i] in (None, "")):
                            low, high = math.ceil(wd * attendance[0] / 100), math.floor(wd * attendance[1] / 100)
                            present[i] = rng.randint(min(low, high), max(low, high))
                            months += 1
                if marks is not None:
                    for n in subs:
                        top = maxes.get(n) or DEFAULT_MAX_MARKS
                        if replace or got.get(n) in (None, ""):
                            a, b = min(marks[0], top), min(marks[1], top)
                            got[n] = rng.randint(a, b)
                            filled += 1
                if not (months or filled):
                    continue
                counts["students"] += 1
                counts["months"] += months
                counts["marks"] += filled
                if apply:
                    if d is None:
                        d = RegisterStudentData(school_id=school_id, student_id=s.id, session=session, sources={})
                        db.add(d)
                        stored[s.id] = d
                    sources = dict(d.sources or {})
                    if months:
                        d.present, sources["present"] = present, stamp
                    if filled:
                        d.marks, sources["marks"] = got, stamp
                    d.sources = sources
            out["stages"][st] = counts
            for k in ("students", "months", "marks"):
                out[k] += counts[k]
        if apply:
            db.commit()
    if apply:
        audit.record(by or f"school_admin:{school_id}", "register_dummy_fill", "register", school_id, None,
                     {"stage": stage or "all", "attendance": attendance, "marks": marks, "replace": replace,
                      "students": out["students"], "months": out["months"], "marks_filled": out["marks"]},
                     school_id=school_id)
    out["applied"] = apply
    return out
