"""
Bulk work on SDMS from Excel, one engine for four of its modules (each step as SDMS's own page does it, read from its
web app): download a sheet with the students -> fill -> upload (checked; nothing sent) -> run, one student first if the
person likes, then the rest - each run only after the person confirms. A row done once is never sent again.

  shift     Class / Section shift      POST api/v2/students/update-class   {studentId, classId, sectionId, classChangeGroup}
                                       (a class change only between Nursery/KG ... and Class I - SDMS's rule)
  dropbox   Send to Dropbox            POST api/v2/students/send-dropbox   {academicYear, lastClassStudied, lastAttendedDate,
                                       tcIssueDate, attendance, studentstatus2, dropoutType, studentPen, studentId}
  import    Import from the Dropbox    POST api/students/import/search/{school} (a read: the student behind a PEN)
                                       POST api/students/import/submit/  {studentId, schoolId, classId, sectionId,
                                       admissionDate, progressionStatusCy, marksCy, attendanceCy}
  aadhaar   AADHAAR corrections        the General save with the AADHAAR as on the card, then UIDAI's check (consent)
Kept encrypted per school: sdms_bulk_<kind>.json (the checked rows and what was done).
"""
import io
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.hpc.xl import keep_text
from backend.services import sdms_aadhaar, udise_sessions
from backend.services.sdms_data import load as load_students
from backend.services.sdms_sync import _read, _write
from backend.udise import client
from backend.udise.sdms import Sdms, SessionEnded

JOBS: Dict[str, Dict[str, Any]] = {}            # "<school>:<kind>" -> the run in progress or last finished
_lock = threading.Lock()
NAME = re.compile(r"^[a-zA-Z.']+( [a-zA-Z.']+)*$")
EARLY_CLASSES = {-3: "Nursery/KG/PP3", -2: "LKG/KG1/PP2", -1: "UKG/KG2/PP1", 1: "I"}   # class shift only among these
CLASS_NAMES = {**EARLY_CLASSES, **{n: r for n, r in zip(range(2, 13), ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])}}
DROPOUT_REASON = {203: "Student Absent for Many Days"}
TC_REASONS = {221: "Family Relocation / Transfer", 222: "Distance from Residence", 223: "Unavailability of Stream / Medium / Subjects",
              224: "Higher Class School Preferred", 225: "Better Academic Opportunities", 226: "Govt–Private School Transfer",
              227: "Others / Unknown Reasons"}
TYPES = {"Left school with TC": 2, "Left school without TC (Dropout)": 1}
SESSIONS = {"Mid session (studying here this year)": "mid", "End session (did not study here this year)": "end"}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _key(school_id: str, kind: str) -> str:
    return f"{school_id}:{kind}"


def _class_id(text: Any) -> Optional[int]:
    t = str(text or "").strip().lower()
    for code, name in CLASS_NAMES.items():
        if t == name.lower() or t in [p.strip().lower() for p in name.split("/")]:
            return code
    return None


def _date(cell: Any, earliest: str = "01/01/2022") -> Optional[str]:
    """DD/MM/YYYY from a cell, between `earliest` and today; None when not a valid date."""
    if hasattr(cell, "strftime"):
        when = datetime(cell.year, cell.month, cell.day)
    else:
        parts = str(cell or "").strip().replace("-", "/").replace(".", "/").split("/")
        if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
            return None
        try:
            when = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        except ValueError:
            return None
    low = datetime.strptime(earliest, "%d/%m/%Y")
    return when.strftime("%d/%m/%Y") if low <= when <= datetime.utcnow() else None


def _int(cell: Any) -> Optional[int]:
    try:
        number = float(str(cell).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _sdms(school_id: str) -> Sdms:
    session = udise_sessions._load(school_id)
    if not (session.get("services", {}).get("sdms") or {}).get("connected"):
        raise client.UdiseError("SDMS is not connected. Press 'Connect UDISE+' first.")
    return Sdms(session)


def sections(sdms: Sdms, school: int) -> Dict[int, Dict[str, int]]:
    """{classId: {section name (upper): sectionId}} as SDMS lists them (api/v2/school/class/sections/{school})."""
    out: Dict[int, Dict[str, int]] = {}
    for c in sdms.get(f"api/v2/school/class/sections/{school}") or []:
        for s in c.get("sectionData") or []:
            sid = s.get("sectionId", s.get("id"))
            name = s.get("sectionDesc") or s.get("sectionName") or s.get("sectionAlias") or s.get("description")
            if sid is not None and name:
                out.setdefault(int(c.get("classId")), {})[str(name).strip().upper()] = int(sid)
    return out


def _sections_from_students(data: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {}
    for s in data["students"]:
        g = s["general"]
        if g.get("classId") is not None and g.get("sectionId") is not None and g.get("sectionDesc"):
            out.setdefault(int(g["classId"]), {})[str(g["sectionDesc"]).strip().upper()] = int(g["sectionId"])
    return out


# ---------------------------------------------------------------------------
# The sheets
# ---------------------------------------------------------------------------

SPECS: Dict[str, Dict[str, Any]] = {
    "shift": {"title": "Class or section shift", "fill": ["New class", "New section"],
              "lists": {"New class": list(CLASS_NAMES.values())},
              "note": "Fill 'New section' (and 'New class' only for Nursery/KG to Class I) for the students to move. Leave a row empty to skip it."},
    "dropbox": {"title": "Send to Dropbox", "fill": ["Type", "Session", "Last class studied", "Last attended date (DD/MM/YYYY)",
                                                     "TC issue date (DD/MM/YYYY)", "Attendance (days)", "Reason"],
                "lists": {"Type": list(TYPES), "Session": list(SESSIONS), "Last class studied": list(CLASS_NAMES.values()),
                          "Reason": list(DROPOUT_REASON.values()) + list(TC_REASONS.values())},
                "note": "Fill a row only for a student who has left. Without TC (dropout) the reason is 'Student Absent for Many Days' and no TC date."},
    "import": {"title": "Import from the Dropbox", "fill": [],
               "lists": {"Class to admit": list(CLASS_NAMES.values())},
               "note": "One row per student to import from the Dropbox: the PEN and date of birth find the student on SDMS."},
    "aadhaar": {"title": "AADHAAR corrections", "fill": ["AADHAAR number (12 digits, from the card)", "Name exactly as on the AADHAAR",
                                                         "Gender (as on the card)", "Date of birth (DD/MM/YYYY, as on the card)",
                                                         "Parent's consent given (Yes/No)"],
                "lists": {"Gender (as on the card)": ["Male", "Female", "Transgender"], "Parent's consent given (Yes/No)": ["Yes", "No"]},
                "note": "Copy the details exactly as printed on each student's AADHAAR card. Saved on SDMS, then checked with UIDAI."},
}
IMPORT_COLUMNS = ["PEN", "Date of birth (DD/MM/YYYY)", "Class to admit", "Section", "Admission date (DD/MM/YYYY)",
                  "Progression status", "Marks (%)", "Attendance (days)"]


def template(school_id: str, kind: str) -> Optional[bytes]:
    data = load_students(school_id)
    if not data or kind not in SPECS:
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter, quote_sheetname
    from openpyxl.worksheet.datavalidation import DataValidation
    spec = SPECS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = spec["title"][:31]
    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    if kind == "import":
        head, rows = IMPORT_COLUMNS, []
    else:
        head = ["PEN", "Student's Name", "Father's Name", "Class", "Section"]
        students = data["students"]
        if kind == "aadhaar":
            head += ["UIDAI's reason"]
            students = [s for s in students if sdms_aadhaar.group_of(s["general"]) in ("mismatch", "retry", "no_aadhaar")]
        head += spec["fill"]
        students = sorted(students, key=lambda s: (s["general"].get("classId") if s["general"].get("classId") is not None else 99,
                                                   str(s["general"].get("sectionDesc") or ""), str(s["general"].get("studentName") or "")))
        rows = [[s["general"].get("studentCodeNat"), s["general"].get("studentName"), s["general"].get("fatherName"),
                 s["general"].get("classDesc"), s["general"].get("sectionDesc")]
                + ([s["general"].get("uuidValidateRemarks")] if kind == "aadhaar" else []) for s in students]
    ws.append([spec["note"]])
    ws["A1"].font = Font(bold=True)
    ws.append(head)
    fixed = 6 if kind == "aadhaar" else 5 if kind != "import" else 0
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="334155" if c.column <= fixed else "0B5FA5")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    last = max(ws.max_row, 3) + (200 if kind == "import" else 0)
    for i, (label, values) in enumerate(spec["lists"].items(), start=1):
        for r, v in enumerate(values, start=1):
            lists.cell(row=r, column=i, value=v)
        col = get_column_letter(head.index(label) + 1)
        dv = DataValidation(type="list", formula1=f"{quote_sheetname('Lists')}!${get_column_letter(i)}$1:${get_column_letter(i)}${len(values)}",
                            allow_blank=True)
        dv.add(f"{col}3:{col}{last}")
        ws.add_data_validation(dv)
    for i, h in enumerate(head, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 28 if "Name" in h or "reason" in h.lower() or h in ("Reason", "Type", "Session") else 16
        if "date" in h.lower() or "AADHAAR number" in h or h == "PEN":
            for r in range(3, last + 1):
                ws.cell(row=r, column=i).number_format = "@"
    ws.freeze_panes = "C3" if kind != "import" else "A3"
    ws.row_dimensions[2].height = 40
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Validate: each filled row -> what will be sent, or what to correct (nothing is sent)
# ---------------------------------------------------------------------------

def _check_shift(cells, s, ctx) -> Dict[str, Any]:
    g = s["general"]
    new_class = _class_id(cells.get("New class")) if str(cells.get("New class") or "").strip() else g.get("classId")
    section = str(cells.get("New section") or "").strip().upper()
    problems = []
    if new_class is None:
        problems.append("New class: a class such as I, UKG/KG2/PP1")
    elif new_class != g.get("classId") and not (new_class in EARLY_CLASSES and g.get("classId") in EARLY_CLASSES):
        problems.append("SDMS allows a class shift only between Nursery/KG ... and Class I; for other classes only the section")
    section_id = ctx["sections"].get(new_class, {}).get(section) if section else (g.get("sectionId") if new_class == g.get("classId") else None)
    if section and section_id is None:
        problems.append(f"New section: '{section}' is not a section of that class on SDMS")
    if not section and new_class != g.get("classId"):
        problems.append("New section: required with a new class")
    if not problems and new_class == g.get("classId") and section_id == g.get("sectionId"):
        return {"skip": True}
    return {"problems": problems, "change": f"{g.get('classDesc')} {g.get('sectionDesc')} → {CLASS_NAMES.get(new_class, new_class)} {section or g.get('sectionDesc')}",
            "body": {"studentId": g["studentId"], "classId": new_class, "sectionId": section_id, "classChangeGroup": 1}}


def _check_dropbox(cells, s, ctx) -> Dict[str, Any]:
    g = s["general"]
    problems = []
    kind = TYPES.get(str(cells.get("Type") or "").strip())
    session = SESSIONS.get(str(cells.get("Session") or "").strip())
    last_class = _class_id(cells.get("Last class studied"))
    attended = _date(cells.get("Last attended date (DD/MM/YYYY)"))
    tc = _date(cells.get("TC issue date (DD/MM/YYYY)")) if str(cells.get("TC issue date (DD/MM/YYYY)") or "").strip() else None
    attendance = _int(cells.get("Attendance (days)"))
    reason_text = str(cells.get("Reason") or "").strip()
    reasons = DROPOUT_REASON if kind == 1 else {k: v for k, v in TC_REASONS.items() if session != "end" or k != 224}
    reason = next((k for k, v in reasons.items() if v.lower() == reason_text.lower()), None)
    if kind is None:
        problems.append("Type: with TC or without TC (dropout)")
    if session is None:
        problems.append("Session: mid session or end session")
    if last_class is None:
        problems.append("Last class studied")
    if attended is None:
        problems.append("Last attended date: DD/MM/YYYY, between 01/01/2022 and today")
    if kind == 2 and tc is None:
        problems.append("TC issue date: DD/MM/YYYY, between 01/01/2022 and today (left with TC)")
    if attendance is None or attendance < 0:
        problems.append("Attendance: a whole number of days")
    if kind is not None and reason is None:
        problems.append("Reason: " + (" / ".join(reasons.values())))
    year = ctx["year_id"] if session == "mid" else (ctx["year_id"] - 1 if ctx["year_id"] else None)
    return {"problems": problems,
            "change": f"{next((k for k, v in TYPES.items() if v == kind), '?')}, {reason_text or '?'}",
            "body": {"academicYear": year, "lastClassStudied": last_class, "lastAttendedDate": attended,
                     "tcIssueDate": tc if kind == 2 else None, "attendance": attendance, "studentstatus2": reason,
                     "dropoutType": kind, "studentPen": g.get("studentCodeNat"), "studentId": g["studentId"]}}


def _check_aadhaar(cells, s, ctx) -> Dict[str, Any]:
    g = s["general"]
    aadhaar = str(cells.get("AADHAAR number (12 digits, from the card)") or "").replace(" ", "")
    name = str(cells.get("Name exactly as on the AADHAAR") or "").strip()
    gender = {"male": 1, "female": 2, "transgender": 3}.get(str(cells.get("Gender (as on the card)") or "").strip().lower())
    dob_cell = cells.get("Date of birth (DD/MM/YYYY, as on the card)")
    dob = _date(dob_cell, "01/01/1943") if str(dob_cell or "").strip() else None
    problems = []
    if not (aadhaar.isdigit() and len(aadhaar) == 12 and aadhaar[0] not in "01"):
        problems.append("AADHAAR number: 12 digits as on the card")
    if not NAME.match(name):
        problems.append("Name: letters, spaces, . and ' only")
    if str(dob_cell or "").strip() and dob is None:
        problems.append("Date of birth: DD/MM/YYYY")
    if str(cells.get("Parent's consent given (Yes/No)") or "").strip().lower() != "yes":
        problems.append("Parent's consent given: Yes (needed for UIDAI's check)")
    return {"problems": problems, "change": "AADHAAR details as on the card, then UIDAI's check",
            "body": {"student_id": g["studentId"], "aadhaar": aadhaar, "name": name,
                     "gender": gender if gender and gender != g.get("gender") else None,
                     "dob": dob if dob and dob != g.get("dob") else None}}


def validate(school_id: str, kind: str, content: bytes, file_name: str) -> Dict[str, Any]:
    data = load_students(school_id)
    if not data:
        return {"ok": False, "error": "Fetch the students from SDMS first."}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read (.xlsx)."}
    title = SPECS[kind]["title"][:31]
    if title not in wb.sheetnames:
        return {"ok": False, "error": f"This is not the '{SPECS[kind]['title']}' sheet. Download it from this page and fill that."}
    ws = wb[title]
    head = [str(c.value).strip() if c.value is not None else "" for c in ws[2]]
    by_pen = {str(s["general"].get("studentCodeNat") or "").strip(): s for s in data["students"]}
    ctx = {"year_id": data.get("year_id"), "sections": _sections_from_students(data)}
    old = _read(school_id, f"sdms_bulk_{kind}.json") or {}
    done = old.get("done", {})
    rows = []
    sdms = None
    if kind in ("import", "shift"):                            # reads: SDMS's sections (a class may have none yet)
        try:
            sdms = _sdms(school_id)
            ctx["school"] = sdms.school_id()
            ctx["sections"] = sections(sdms, ctx["school"]) or ctx["sections"]
        except client.UdiseError as exc:
            return {"ok": False, "error": str(exc)}
    for n, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        cells = dict(zip(head, values))
        pen = str(cells.get("PEN") or "").strip()
        if not pen:
            continue
        if kind == "import":
            row = _check_import(sdms, ctx, cells, pen)
        else:
            filled = [h for h in SPECS[kind]["fill"] if str(cells.get(h) or "").strip()]
            if not filled:
                continue                                       # an untouched row: nothing to do for this student
            s = by_pen.get(pen)
            if s is None:
                rows.append({"row": n, "pen": pen, "name": cells.get("Student's Name"), "problems": ["PEN not one of this school's students"]})
                continue
            row = {"shift": _check_shift, "dropbox": _check_dropbox, "aadhaar": _check_aadhaar}[kind](cells, s, ctx)
            if row.get("skip"):
                continue
            row.update(name=s["general"].get("studentName"), cls=f"{s['general'].get('classDesc')} {s['general'].get('sectionDesc')}")
        fingerprint = f"{pen}|{row.get('change')}"
        rows.append({"row": n, "pen": pen, "name": row.get("name"), "class": row.get("cls"), "change": row.get("change"),
                     "problems": row.get("problems", []), "body": row.get("body"), "fingerprint": fingerprint,
                     "done": done.get(fingerprint)})
    _write(school_id, f"sdms_bulk_{kind}.json", {"file_name": file_name, "checked_at": _now(), "rows": rows, "done": done})
    return {"ok": True, **public(school_id, kind)}


def _check_import(sdms: Sdms, ctx, cells, pen) -> Dict[str, Any]:
    problems = []
    dob = _date(cells.get("Date of birth (DD/MM/YYYY)"), "01/01/1943")
    class_id = _class_id(cells.get("Class to admit"))
    section = str(cells.get("Section") or "").strip().upper()
    admitted = _date(cells.get("Admission date (DD/MM/YYYY)"))
    marks, attendance = _int(cells.get("Marks (%)")), _int(cells.get("Attendance (days)"))
    status_text = str(cells.get("Progression status") or "").strip()
    if dob is None:
        problems.append("Date of birth: DD/MM/YYYY")
    if class_id is None:
        problems.append("Class to admit")
    section_id = ctx["sections"].get(class_id, {}).get(section) if class_id is not None else None
    if section_id is None:
        problems.append(f"Section: '{section}' is not a section of that class on SDMS")
    if admitted is None:
        problems.append("Admission date: DD/MM/YYYY, not in the future")
    if marks is None or not 0 <= marks <= 100:
        problems.append("Marks: a whole number 0 to 100")
    if attendance is None or not 1 <= attendance <= 250:
        problems.append("Attendance: 1 to 250 days")
    found, name = None, None
    if dob is not None:
        try:                                                   # a read: the Dropbox student behind this PEN
            answer = sdms.post_answer(f"api/students/import/search/{ctx['school']}", {"searchType": 1, "studentCodeNat": pen, "dob": dob})
            rows = answer.get("data") if answer.get("status") else None
            found = rows[0] if isinstance(rows, list) and rows else None
            if found is None:
                problems.append("SDMS: " + str(((answer.get("error") or {}) if isinstance(answer.get("error"), dict) else {}).get("message")
                                               or "no Dropbox student with this PEN and date of birth"))
            else:
                name = found.get("studentName")
        except client.UdiseError as exc:
            problems.append(str(exc))
    status_code = None
    if class_id is not None and found is not None:
        try:
            promoted = found.get("classToPromoted", class_id)        # as SDMS's import page asks: the class it offers
            options = sdms.get(f"api/school/progression-status/{ctx['school']}/{promoted}") or {}
            status_code = next((k for k, v in options.items() if str(v).strip().lower() == status_text.lower()), None)
            if status_code is None:
                problems.append("Progression status: one of " + ", ".join(map(str, options.values())))
        except client.UdiseError as exc:
            problems.append(str(exc))
    return {"problems": problems, "name": name, "cls": f"{CLASS_NAMES.get(class_id, '?')} {section}",
            "change": f"import into {CLASS_NAMES.get(class_id, '?')} {section}",
            "body": {"studentId": (found or {}).get("studentId"), "schoolId": ctx["school"], "classId": class_id,
                     "progressionStatusCy": status_code, "marksCy": str(marks if marks is not None else 0),
                     "attendanceCy": attendance, "sectionId": section_id, "admissionDate": admitted}}


def public(school_id: str, kind: str) -> Optional[Dict[str, Any]]:
    plan = _read(school_id, f"sdms_bulk_{kind}.json")
    if not plan or plan.get("rows") is None:
        return None
    done = plan.get("done", {})
    rows = [{**{k: v for k, v in r.items() if k not in ("body", "fingerprint")}, "done": done.get(r.get("fingerprint"))}
            for r in plan["rows"]]
    return {"file_name": plan["file_name"], "checked_at": plan["checked_at"], "rows": rows,
            "ready": sum(1 for r in rows if not r["problems"] and not r["done"]),
            "with_problems": sum(1 for r in rows if r["problems"]),
            "done": sum(1 for r in rows if r["done"])}


# ---------------------------------------------------------------------------
# Run: only the checked rows, one first if the person likes; never one twice
# ---------------------------------------------------------------------------

def state(school_id: str, kind: str) -> Dict[str, Any]:
    with _lock:
        job = dict(JOBS.get(_key(school_id, kind)) or {}) or None
    return {"plan": public(school_id, kind), "job": job}


def start(school_id: str, kind: str, only_rows: Optional[List[int]] = None) -> Dict[str, Any]:
    plan = _read(school_id, f"sdms_bulk_{kind}.json")
    if not plan:
        return {"started": False, "error": "Upload and check the filled sheet first."}
    done = plan.get("done", {})                                # what was sent since the sheet was checked counts too
    todo = [r for r in plan["rows"] if not r["problems"] and not done.get(r["fingerprint"]) and (only_rows is None or r["row"] in only_rows)]
    if not todo:
        return {"started": False, "error": "Nothing to send: every row has something to correct, or was done already."}
    try:
        sdms = _sdms(school_id)
    except client.UdiseError as exc:
        return {"started": False, "error": str(exc)}
    key = _key(school_id, kind)
    with _lock:
        if (JOBS.get(key) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "This is already running."}
        JOBS[key] = {"status": "RUNNING", "done": 0, "total": len(todo), "results": [], "started_at": _now(),
                     "finished_at": None, "error": None}
    threading.Thread(target=_run, args=(school_id, kind, sdms, todo), daemon=True, name=f"bulk-{kind}").start()
    return {"started": True, "students": len(todo)}


def _send(school_id: str, kind: str, sdms: Sdms, body: Dict[str, Any]) -> str:
    """One row: SDMS's own call. Returns what SDMS said; a refusal raises UdiseError with SDMS's words."""
    if kind == "aadhaar":
        found = sdms_aadhaar.correct(school_id, body["student_id"], body["aadhaar"], body["name"], body["gender"], body["dob"])
        if not found.get("ok"):
            raise client.UdiseError(found.get("error") or "Not saved")
        return "Saved and verified with UIDAI" if found.get("verified") else f"Saved; UIDAI: {found.get('reason') or found.get('status')}"
    path = {"shift": "api/v2/students/update-class", "dropbox": "api/v2/students/send-dropbox",
            "import": "api/students/import/submit/"}[kind]
    answer = sdms.post_answer(path, body)
    if answer.get("status") is not True:
        error = answer.get("error") if isinstance(answer.get("error"), dict) else {}
        fields = (error.get("data") or {}).get("errorFields") if isinstance(error.get("data"), dict) else None
        raise client.UdiseError("SDMS did not accept it: " + str(error.get("message") or answer.get("message") or "no reason given")
                                + (f" ({fields})" if fields else ""))
    return answer.get("message") or ("Transaction " + str(answer.get("tnxReqNo")) if answer.get("tnxReqNo") else "Done")


def _mark_done(school_id: str, kind: str, fingerprint: str) -> None:
    """Records a row SDMS accepted, so it is never sent again. Never writes over the sheet when it cannot be read."""
    for _ in range(5):
        plan = _read(school_id, f"sdms_bulk_{kind}.json")
        if plan is not None:
            plan.setdefault("done", {})[fingerprint] = _now()
            _write(school_id, f"sdms_bulk_{kind}.json", plan)
            return
        time.sleep(0.2)
    raise RuntimeError("SDMS accepted the row but it could not be marked done; stopped so nothing is sent twice")


def _run(school_id: str, kind: str, sdms: Sdms, todo: List[Dict[str, Any]]) -> None:
    from backend.services import audit
    key = _key(school_id, kind)
    try:
        for r in todo:
            result = {"row": r["row"], "name": r["name"], "change": r["change"], "message": None, "error": None}
            try:
                result["message"] = _send(school_id, kind, sdms, r["body"])
                _mark_done(school_id, kind, r["fingerprint"])
            except SessionEnded:
                raise
            except client.UdiseError as exc:
                result["error"] = str(exc)
            audit.record(f"school_admin:{school_id}", f"sdms_bulk_{kind}", "student", r["pen"], None, {"ok": not result["error"]})
            with _lock:
                JOBS[key]["results"].append(result)
                JOBS[key]["done"] += 1
            time.sleep(0.5)
        with _lock:
            JOBS[key].update(status="COMPLETED", finished_at=_now())
    except SessionEnded as exc:
        with _lock:
            JOBS[key].update(status="FAILED", error=str(exc), finished_at=_now())
    except Exception as exc:
        with _lock:
            JOBS[key].update(status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())
