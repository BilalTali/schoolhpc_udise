"""
A school's students as SDMS holds them for the current session: fetched in the background (with progress), kept
encrypted at data/sessions/school_<id>/sdms_current.json (it holds personal details), shown in the web app and
downloadable as Excel for checking. Read only: nothing is written to SDMS.
"""
import io
import json
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.hpc.xl import keep_text
from backend.services import secrets_box, udise_sessions
from backend.services.hpc_sessions import session_dir
from backend.udise import client
from backend.udise import sdms_form
from backend.udise.sdms import Sdms, SessionEnded, session_label

JOBS: Dict[str, Dict[str, Any]] = {}             # school id -> the fetch in progress or last finished
_lock = threading.Lock()


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _file(school_id: str):
    return session_dir("school", school_id) / "sdms_current.json"


def load(school_id: str) -> Optional[Dict[str, Any]]:
    path = _file(school_id)
    if not path.exists():
        return None
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _save(school_id: str, data: Dict[str, Any]) -> None:
    path = _file(school_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    tmp.replace(path)


def progress(school_id: str) -> Dict[str, Any]:
    with _lock:
        job = dict(JOBS.get(school_id) or {})
    saved = load(school_id)
    return {"job": job or None,
            "saved": {"fetched_at": saved["fetched_at"], "session": session_label({"yearId": saved.get("year_id")}),
                      "students": len(saved["students"]),
                      "problems": saved.get("problems", 0)} if saved else None}


def start(school_id: str) -> Dict[str, Any]:
    saved_session = udise_sessions._load(school_id)
    if not (saved_session.get("services", {}).get("sdms") or {}).get("connected"):
        return {"started": False, "error": "SDMS is not connected. Press 'Connect UDISE+' on the Home page first."}
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "A fetch is already running."}
        JOBS[school_id] = {"status": "RUNNING", "step": "Opening SDMS", "done": 0, "total": 0, "started_at": _now(),
                           "finished_at": None, "error": None}
    threading.Thread(target=_run, args=(school_id, saved_session), daemon=True, name=f"sdms-fetch-{school_id[:8]}").start()
    return {"started": True}


def _step(school_id: str, **kw) -> None:
    with _lock:
        JOBS[school_id].update(kw)


def _run(school_id: str, saved_session: Dict[str, Any]) -> None:
    sdms = Sdms(saved_session)
    try:
        sid = sdms.school_id()
        school = sdms.school(sid)
        _step(school_id, step="Reading the classes and the school's lists")
        classes = sdms.classes(sid)
        masters = sdms_form.masters_from(school, sdms.mother_tongues(school.get("stateId")), sdms.media(sid))
        _step(school_id, step="Reading every student's profile")
        general = sdms.students(sid)
        _step(school_id, step="Reading each student's enrolment and facility", total=len(general))
        students, problems = [], 0
        for i, g in enumerate(general, start=1):
            entry = {"general": g, "enrolment": None, "facility": None, "problems": []}
            for part, read in (("enrolment", sdms.enrolment), ("facility", sdms.facility)):
                try:
                    entry[part] = read(g["studentId"])
                except SessionEnded:
                    raise
                except client.UdiseError as exc:          # one student's part: noted, the rest go on
                    entry["problems"].append(f"{part}: {exc}")
            problems += bool(entry["problems"])
            students.append(entry)
            _step(school_id, done=i)
        data = {"fetched_at": _now(), "session": session_label(school), "year_id": school.get("yearId"),
                "school": {k: school.get(k) for k in ("schoolId", "udiseSchCode", "schoolName", "classFrom", "classTo",
                                                      "classFromDesc", "classToDesc", "sessionStartDate", "sessionEndDate")},
                "classes": classes, "students": students, "problems": problems, "masters": masters}
        _save(school_id, data)
        from backend.services import audit
        audit.record(f"school_admin:{school_id}", "sdms_fetch", "udise", school_id, None,
                     {"students": len(students), "classes": len(classes), "problems": problems, "session": data["session"]})
        _step(school_id, status="COMPLETED", step="Done", finished_at=_now())
    except client.UdiseError as exc:
        _step(school_id, status="FAILED", error=str(exc), finished_at=_now())
    except Exception as exc:                          # never leave a fetch "running" for ever
        _step(school_id, status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())


# ---------------------------------------------------------------------------
# What the web app shows, and the Excel for checking
# ---------------------------------------------------------------------------

FORM_STATUS = {6: "Completed", 0: "Not started"}   # SDMS's own: anything else is "In progress"


def view(school_id: str) -> Optional[Dict[str, Any]]:
    """The fetched data for the page: the classes, and each student with the main columns and the whole form."""
    data = load(school_id)
    if not data:
        return None
    masters = data.get("masters") or {}
    rows = []
    for s in data["students"]:
        g, e = s["general"], s.get("enrolment") or {}
        rows.append({"student_id": g.get("studentId"), "pen": g.get("studentCodeNat"), "name": g.get("studentName"),
                     "class_id": g.get("classId"), "class": g.get("classDesc"), "section": g.get("sectionDesc"),
                     "gender": sdms_form.GENDER.get(g.get("gender"), ""), "dob": g.get("dob"),
                     "father": g.get("fatherName"), "mother": g.get("motherName"), "mobile": g.get("primaryMobile"),
                     "admission_no": e.get("admnNumber") or g.get("admnNumber"), "aadhaar_status": g.get("uuidStatusDesc"),
                     "form": FORM_STATUS.get(g.get("formStatus"), "In progress"),
                     "problems": s.get("problems") or [], "details": sdms_form.as_form(s, masters)})
    rows.sort(key=lambda r: (r["class_id"] if r["class_id"] is not None else 99, str(r["section"] or ""), str(r["name"] or "")))
    return {"fetched_at": data["fetched_at"], "session": session_label({"yearId": data.get("year_id")}),
            "school": data["school"], "has_lists": bool(masters),
            "classes": [{"class_id": c.get("classId"), "class": c.get("classDesc"), "boys": c.get("totalBoys"),
                         "girls": c.get("totalGirls"), "trans": c.get("totalTrans"), "total": c.get("totalEnrollment"),
                         "incomplete": c.get("totalIncompleted")} for c in data["classes"]],
            "students": rows}


def excel(school_id: str) -> Optional[bytes]:
    """The student form as SDMS shows it, one row per student: the tabs as column groups, the questions as columns
    (SDMS's own labels and order), the answers in words. A sheet with all, one per class, and the class totals."""
    data = load(school_id)
    if not data:
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    masters = data.get("masters") or {}
    sections = [(section, [label for label, *_ in fields]) for section, fields in sdms_form.FORM]
    labels = [label for _, ls in sections for label in ls] + ["Problems reading"]
    rows = []
    for s in data["students"]:
        values = [f["value"] for sec in sdms_form.as_form(s, masters) for f in sec["fields"]]
        rows.append(((s["general"].get("classId") if s["general"].get("classId") is not None else 99,
                      str(s["general"].get("sectionDesc") or ""), str(s["general"].get("studentName") or "")),
                     s["general"].get("classDesc") or "No class", values + ["; ".join(s.get("problems") or [])]))
    rows.sort(key=lambda t: t[0])
    fills = [PatternFill("solid", fgColor=c) for c in ("334155", "0B5FA5", "046A38", "B45309")]
    white = Font(bold=True, color="FFFFFF")

    def sheet(ws, these):
        col = 1
        for i, (section, ls) in enumerate(sections):          # row 1: the tab; row 2: the question
            ws.cell(row=1, column=col, value=section)
            if len(ls) > 1:
                ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + len(ls) - 1)
            for j, label in enumerate(ls):
                c = ws.cell(row=2, column=col + j, value=label)
                c.font, c.fill = white, fills[i % len(fills)]
                c.alignment = Alignment(wrap_text=True, vertical="top")
                ws.cell(row=1, column=col + j).fill = fills[i % len(fills)]
            ws.cell(row=1, column=col).font = white
            col += len(ls)
        ws.cell(row=2, column=col, value="Problems reading").font = Font(bold=True)
        for _, _, values in these:
            ws.append(values)
        ws.freeze_panes = "F3"
        ws.row_dimensions[2].height = 60
        for i, label in enumerate(labels, start=1):
            ws.column_dimensions[get_column_letter(i)].width = 32 if label.startswith("Student's Name") else 18

    wb = Workbook()
    summary = wb.active
    summary.title = "Classes"
    summary.append([f"SDMS student forms, session {session_label({'yearId': data.get('year_id')})}, fetched "
                    f"{data['fetched_at'][:16].replace('T', ' ')} UTC"])
    summary["A1"].font = Font(bold=True, size=13)
    summary.append([])
    summary.append(["Class", "Boys", "Girls", "Transgender", "Total", "Forms incomplete"])
    for c in summary[3]:
        c.font, c.fill = white, fills[1]
    for c in data["classes"]:
        summary.append([c.get("classDesc"), c.get("totalBoys"), c.get("totalGirls"), c.get("totalTrans"),
                        c.get("totalEnrollment"), c.get("totalIncompleted")])
    summary.column_dimensions["A"].width = 24
    sheet(wb.create_sheet("All students"), rows)
    by_class: Dict[Any, list] = {}
    for item in rows:
        by_class.setdefault(item[1], []).append(item)
    for name, these in by_class.items():
        sheet(wb.create_sheet(re.sub(r"[\\/*?:\[\]]", "-", str(name))[:31]), these)   # Excel refuses these in names
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()


def completion_excel(school_id: str) -> Optional[bytes]:
    """One sheet to complete the SDMS forms: Class, Section, Name, Father's name and PEN to find each student, then
    only the fields SDMS requires, with their answers in words. A required cell that is empty or wrong is
    highlighted, and "To complete" lists them per student."""
    data = load(school_id)
    if not data:
        return None
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    masters = data.get("masters") or {}
    fixed = ["Class", "Section", "Student's Name", "Father's Name (parentage)", "PEN", "Form status", "To complete"]
    required = [(tab, label) for tab, label, *_ in sdms_form.REQUIRED]
    wb = Workbook()
    ws = wb.active
    ws.title = "To complete"
    dark, white = PatternFill("solid", fgColor="334155"), Font(bold=True, color="FFFFFF")
    tab_fill = {"General": PatternFill("solid", fgColor="0B5FA5"), "Enrolment": PatternFill("solid", fgColor="046A38"),
                "Other": PatternFill("solid", fgColor="B45309")}
    tab_name = {"General": "1. General Information", "Enrolment": "2. Enrolment Details", "Other": "3. Other Details"}
    # row 1: the tab of each required field; row 2: the field
    ws.cell(row=1, column=1, value="Student")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(fixed))
    col = len(fixed) + 1
    for tab in ("General", "Enrolment", "Other"):
        n = sum(1 for t, _ in required if t == tab)
        ws.cell(row=1, column=col, value=tab_name[tab])
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + n - 1)
        for c in range(col, col + n):
            ws.cell(row=1, column=c).fill = tab_fill[tab]
        col += n
    for c in range(1, len(fixed) + 1):
        ws.cell(row=1, column=c).fill = dark
    for i, label in enumerate(fixed + [label for _, label in required], start=1):
        cell = ws.cell(row=2, column=i, value=label)
        cell.font, cell.alignment = white, Alignment(wrap_text=True, vertical="top")
        cell.fill = dark if i <= len(fixed) else tab_fill[required[i - len(fixed) - 1][0]]
    for c in ws[1]:
        c.font = white
    todo_fill = PatternFill("solid", fgColor="FEF3C7")
    rows = sorted(data["students"], key=lambda s: (s["general"].get("classId") if s["general"].get("classId") is not None else 99,
                                                   str(s["general"].get("sectionDesc") or ""), str(s["general"].get("studentName") or "")))
    for r, s in enumerate(rows, start=3):
        g = s["general"]
        checks = sdms_form.completion(s, masters)
        todo = [f"{c['label']} ({c['issue']})" for c in checks if c["issue"]]
        values = [g.get("classDesc"), g.get("sectionDesc"), g.get("studentName"), g.get("fatherName"), g.get("studentCodeNat"),
                  FORM_STATUS.get(g.get("formStatus"), "In progress"), f"{len(todo)}: " + "; ".join(todo) if todo else "Complete"]
        for i, v in enumerate(values + [c["value"] for c in checks], start=1):
            ws.cell(row=r, column=i, value=v)
        if todo:
            ws.cell(row=r, column=len(fixed)).fill = todo_fill
        for i, c in enumerate(checks, start=len(fixed) + 1):
            if c["issue"]:
                cell = ws.cell(row=r, column=i)
                cell.fill = todo_fill
                cell.comment = Comment(c["issue"], "TeacherAssist")
    ws.freeze_panes = ws.cell(row=3, column=6)
    ws.auto_filter.ref = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"
    ws.row_dimensions[2].height = 48
    for i in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = {3: 30, 4: 26, 7: 45}.get(i, 16)
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()


def completion_summary(school_id: str) -> Optional[Dict[str, Any]]:
    """How many students still have required fields to fill, and which fields most often."""
    data = load(school_id)
    if not data:
        return None
    masters = data.get("masters") or {}
    per_field: Dict[str, int] = {}
    students_todo = 0
    for s in data["students"]:
        issues = [c for c in sdms_form.completion(s, masters) if c["issue"]]
        students_todo += bool(issues)
        for c in issues:
            per_field[f"{c['label']} ({c['issue']})"] = per_field.get(f"{c['label']} ({c['issue']})", 0) + 1
    return {"students": len(data["students"]), "to_complete": students_todo,
            "fields": sorted(per_field.items(), key=lambda kv: -kv[1])}


def admission_template(school_id: str) -> Optional[bytes]:
    """A sheet for new admissions: one row per new student - the Add Student form's fields, then the rest SDMS
    requires before the form is complete. Drop-downs in SDMS's words (lists on a hidden sheet); required columns
    are marked *. Nothing about existing students is in it. Editable throughout."""
    data = load(school_id)
    if not data:
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter, quote_sheetname
    from openpyxl.worksheet.datavalidation import DataValidation
    classes = [c.get("classDesc") for c in data["classes"] if c.get("classDesc")]
    lists = sdms_form.admission_lists(data.get("masters") or {}, classes)
    wb = Workbook()
    ws = wb.active
    ws.title = "New students"
    lists_ws = wb.create_sheet("Lists")
    lists_ws.sheet_state = "hidden"
    refs = {}
    for i, (name, values) in enumerate(lists.items(), start=1):
        letter = get_column_letter(i)
        lists_ws.cell(row=1, column=i, value=name)
        for r, v in enumerate(values, start=2):
            lists_ws.cell(row=r, column=i, value=v)
        refs[name] = f"{quote_sheetname('Lists')}!${letter}$2:${letter}${max(2, len(values) + 1)}"
    groups = [("Add Student (SDMS form)", sdms_form.ADD_STUDENT, "0B5FA5"), ("Rest of the student form", sdms_form.REST_OF_FORM, "046A38")]
    rows_for_entry = 200
    col = 1
    ws.cell(row=1, column=1, value=f"New admissions, session {session_label({'yearId': data.get('year_id')})}. One row per new "
                                     "student. Columns marked * are required by SDMS. Dates as DD/MM/YYYY.")
    ws.cell(row=1, column=1).font = Font(bold=True)
    for title, fields, colour in groups:
        ws.cell(row=2, column=col, value=title)
        ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + len(fields) - 1)
        fill = PatternFill("solid", fgColor=colour)
        for j, (label, required, kind) in enumerate(fields):
            c = col + j
            ws.cell(row=2, column=c).fill = fill
            head = ws.cell(row=3, column=c, value=f"{label}{' *' if required else ''}")
            head.font, head.fill = Font(bold=True, color="FFFFFF"), fill
            head.alignment = Alignment(wrap_text=True, vertical="top")
            ws.column_dimensions[get_column_letter(c)].width = 34 if kind == "mother_tongue" else 22
            letter = get_column_letter(c)
            if kind in refs:
                dv = DataValidation(type="list", formula1=refs[kind], allow_blank=True, showErrorMessage=True,
                                    errorTitle="Choose from the list", error="Pick one of SDMS's choices.")
                dv.add(f"{letter}4:{letter}{3 + rows_for_entry}")
                ws.add_data_validation(dv)
            if kind in ("digits", "date"):
                for r in range(4, 4 + rows_for_entry):
                    ws.cell(row=r, column=c).number_format = "@"          # keep leading zeros / dates as typed
        ws.cell(row=2, column=col).font = Font(bold=True, color="FFFFFF")
        col += len(fields)
    ws.row_dimensions[3].height = 60
    ws.freeze_panes = "D4"
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()
