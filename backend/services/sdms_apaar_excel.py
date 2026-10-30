"""
APAAR by Excel: the status report (completed with their APAAR IDs, pending with SDMS's reason and what to do next),
and generation from a filled consent sheet - upload -> validate (nothing sent) -> generate (after the person confirms,
one student first if they like). Each row needs the parent's physical consent written in, and "Yes" in "Consent
signed": the app never assumes a consent. Kept encrypted: sdms_apaar_plan.json (the consents, for the generation).
"""
import io
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.hpc.xl import keep_text
from backend.services import sdms_aadhaar
from backend.services.sdms_data import load as load_students
from backend.services.sdms_sync import _read, _write

JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
PLAN = "sdms_apaar_plan.json"
CONSENT_COLUMNS = ["Consent given by", "Consenter's name", "ID proof type", "ID proof number",
                   "Place of physical consent", "Date of physical consent (DD/MM/YYYY)", "Consent signed (Yes/No)"]
NEXT_STEP = {"retry": "Verify the AADHAAR again (step 1)", "mismatch": "Correct the details from the AADHAAR card, then verify (step 2)",
             "no_aadhaar": "Enter the student's AADHAAR on SDMS first"}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _rows(school_id: str) -> Optional[List[Dict[str, Any]]]:
    view = sdms_aadhaar.overview(school_id)
    if view is None:
        return None
    data = load_students(school_id)
    fathers = {s["general"].get("studentId"): s["general"].get("fatherName") for s in data["students"]}
    return [{**r, "father": fathers.get(r["student_id"])} for r in view["students"]]


def _next_step(r: Dict[str, Any]) -> str:
    if r["apaar_ready"]:
        return "Generate the APAAR ID with the parent's consent (step 3 / consent sheet)"
    if r["group"] == "mismatch" and "invalid aadhaar" in str(r["reason"] or "").lower():
        return "The AADHAAR number on SDMS is wrong: enter it again from the card (step 2)"
    return NEXT_STEP.get(r["group"], "Check the student's form on SDMS (PEN missing)")


def status_excel(school_id: str) -> Optional[bytes]:
    """Two sheets: Completed (APAAR ID and its date) and Pending (SDMS's AADHAAR and APAAR reasons, what to do next)."""
    rows = _rows(school_id)
    if rows is None:
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    white = Font(bold=True, color="FFFFFF")

    def sheet(ws, head, values, colour):
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill, c.alignment = white, PatternFill("solid", fgColor=colour), Alignment(wrap_text=True, vertical="top")
        for v in values:
            ws.append(v)
        ws.freeze_panes = "D2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(head))}{max(2, ws.max_row)}"
        for i, h in enumerate(head, start=1):
            ws.column_dimensions[get_column_letter(i)].width = 44 if h in ("What to do next", "APAAR (SDMS's message)", "AADHAAR reason (UIDAI)") else 18 if i > 3 else 26
        ws.row_dimensions[1].height = 32

    wb = Workbook()
    done = [r for r in rows if r["apaar_id"]]
    pending = [r for r in rows if not r["apaar_id"]]
    sheet(wb.active, ["Class", "Section", "Student's Name", "Father's Name", "PEN", "APAAR ID", "Generated on"],
          [[r["class"], r["section"], r["name"], r["father"], r["pen"], r["apaar_id"], r.get("apaar_date")] for r in done], "046A38")
    wb.active.title = f"Completed ({len(done)})"
    sheet(wb.create_sheet(f"Pending ({len(pending)})"),
          ["Class", "Section", "Student's Name", "Father's Name", "PEN", "AADHAAR status", "AADHAAR reason (UIDAI)",
           "APAAR (SDMS's message)", "What to do next"],
          [[r["class"], r["section"], r["name"], r["father"], r["pen"], r["status"], r["reason"], r["apaar_status"] or "Not requested",
            _next_step(r)] for r in pending], "B45309")
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()


def consent_template(school_id: str) -> Optional[bytes]:
    """The students ready for an APAAR ID (a PEN, a verified AADHAAR, none yet), with the consent columns to fill."""
    rows = _rows(school_id)
    if rows is None:
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter, quote_sheetname
    from openpyxl.worksheet.datavalidation import DataValidation
    ready = [r for r in rows if r["apaar_ready"]]
    wb = Workbook()
    ws = wb.active
    ws.title = "APAAR consent"
    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    for i, values in enumerate([list(sdms_aadhaar.RELATIONS.values()), list(sdms_aadhaar.ID_TYPES.values()), ["Yes", "No"]], start=1):
        for r, v in enumerate(values, start=1):
            lists.cell(row=r, column=i, value=v)
    head = ["PEN", "Class", "Section", "Student's Name", "Father's Name"] + CONSENT_COLUMNS
    ws.append(["Fill one row per student whose father, mother or legal guardian signed the physical consent for the APAAR ID. "
               "Write 'Yes' in the last column only then. Rows without 'Yes' are left out."])
    ws["A1"].font = Font(bold=True)
    ws.append(head)
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="334155" if c.column <= 5 else "0B5FA5")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in ready:
        ws.append([r["pen"], r["class"], r["section"], r["name"], r["father"]])
    last = max(3, ws.max_row)
    for col, ref in ((6, "$A$1:$A$3"), (8, "$B$1:$B$5"), (12, "$C$1:$C$2")):
        letter = get_column_letter(col)
        dv = DataValidation(type="list", formula1=f"{quote_sheetname('Lists')}!{ref}", allow_blank=True)
        dv.add(f"{letter}3:{letter}{last}")
        ws.add_data_validation(dv)
    for row in ws.iter_rows(min_row=3, min_col=9, max_col=11):
        for c in row:
            c.number_format = "@"
    ws.freeze_panes = "F3"
    ws.row_dimensions[2].height = 36
    for i, w in enumerate([14, 10, 8, 28, 26, 16, 26, 16, 18, 20, 18, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    wb.save(out)
    return out.getvalue()


def _date(cell: Any) -> Optional[str]:
    """YYYY-MM-DD (what generation takes) from DD/MM/YYYY or an Excel date; a date not in the future."""
    if hasattr(cell, "strftime"):
        y, m, d = cell.year, cell.month, cell.day
    else:
        parts = str(cell or "").strip().replace("-", "/").replace(".", "/").split("/")
        if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
            return None
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
    try:
        when = datetime(y, m, d)
    except ValueError:
        return None
    return when.strftime("%Y-%m-%d") if when <= datetime.utcnow() else None


def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    rows = _rows(school_id)
    if rows is None:
        return {"ok": False, "error": "Fetch the students and read the APAAR status first."}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read. Upload the filled consent sheet (.xlsx)."}
    if "APAAR consent" not in wb.sheetnames:
        return {"ok": False, "error": "This is not the consent sheet (its sheet 'APAAR consent' is missing). Download it and fill that."}
    ws = wb["APAAR consent"]
    head = [str(c.value).strip() if c.value is not None else "" for c in ws[2]]
    by_pen = {str(r["pen"] or "").strip(): r for r in rows}
    relations = {v.lower(): k for k, v in sdms_aadhaar.RELATIONS.items()}
    id_types = {v.lower(): k for k, v in sdms_aadhaar.ID_TYPES.items()}
    old = _read(school_id, PLAN) or {}
    done = old.get("done", {})                                # student id -> APAAR ID (never sent twice)
    plan = []
    for n, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        cells = dict(zip(head, values))
        pen = str(cells.get("PEN") or "").strip()
        if not pen:
            continue
        signed = str(cells.get("Consent signed (Yes/No)") or "").strip().lower()
        if signed != "yes":
            continue                                          # no signed consent: not a row to send
        r = by_pen.get(pen)
        problems = []
        if r is None:
            plan.append({"row": n, "pen": pen, "name": cells.get("Student's Name"), "problems": ["PEN not one of this school's students"]})
            continue
        if r["apaar_id"] or str(r["student_id"]) in done:
            plan.append({"row": n, "pen": pen, "name": r["name"], "class": f"{r['class']} {r['section']}", "student_id": r["student_id"],
                         "problems": [], "already": r["apaar_id"] or done.get(str(r["student_id"]))})
            continue
        if not r["apaar_ready"]:
            problems.append("not ready on SDMS: " + _next_step(r))
        relation = relations.get(str(cells.get("Consent given by") or "").strip().lower())
        id_type = id_types.get(str(cells.get("ID proof type") or "").strip().lower())
        name = str(cells.get("Consenter's name") or "").strip()
        id_no = str(cells.get("ID proof number") or "").strip().replace(" ", "")
        place = str(cells.get("Place of physical consent") or "").strip()
        date = _date(cells.get("Date of physical consent (DD/MM/YYYY)"))
        if relation is None:
            problems.append("Consent given by: Father, Mother or Legal Guardian")
        if not sdms_aadhaar.NAME.match(name):
            problems.append("Consenter's name: letters only")
        if id_type is None:
            problems.append("ID proof type: from the list")
        elif not id_no:
            problems.append("ID proof number")
        elif id_type == 1 and not (id_no.isdigit() and len(id_no) == 12):
            problems.append("ID proof number: an AADHAAR has 12 digits")
        elif id_type == 2 and not re.match(r"^[A-Za-z]{5}\d{4}[A-Za-z]$", id_no):
            problems.append("ID proof number: a PAN is like ABCDE1234F")
        if not place:
            problems.append("Place of physical consent")
        if date is None:
            problems.append("Date of physical consent: DD/MM/YYYY, not in the future")
        plan.append({"row": n, "pen": pen, "name": r["name"], "class": f"{r['class']} {r['section']}", "student_id": r["student_id"],
                     "problems": problems, "already": None,
                     "consent": {"relation": relation, "name": name, "id_type": id_type, "id_no": id_no, "place": place, "date": date}})
    _write(school_id, PLAN, {"file_name": file_name, "checked_at": _now(), "rows": plan, "done": done})
    return {"ok": True, **public(_read(school_id, PLAN))}


def public(plan: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{k: v for k, v in r.items() if k != "consent"} for r in plan["rows"]]   # consents are not shown back
    return {"file_name": plan["file_name"], "checked_at": plan["checked_at"], "rows": rows,
            "ready": sum(1 for r in plan["rows"] if not r["problems"] and not r.get("already")),
            "with_problems": sum(1 for r in plan["rows"] if r["problems"]),
            "already": sum(1 for r in plan["rows"] if r.get("already"))}


def state(school_id: str) -> Dict[str, Any]:
    plan = _read(school_id, PLAN)
    with _lock:
        job = dict(JOBS.get(school_id) or {}) or None
    return {"plan": public(plan) if plan and plan.get("rows") is not None else None, "job": job}


def start(school_id: str, rows: Optional[List[int]] = None) -> Dict[str, Any]:
    plan = _read(school_id, PLAN)
    if not plan:
        return {"started": False, "error": "Upload and check the filled consent sheet first."}
    todo = [r for r in plan["rows"] if not r["problems"] and not r.get("already") and (rows is None or r["row"] in rows)]
    if not todo:
        return {"started": False, "error": "Nothing to generate: no row with a signed consent and nothing to correct."}
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "APAAR generation is already running."}
        JOBS[school_id] = {"status": "RUNNING", "done": 0, "total": len(todo), "results": [], "started_at": _now(),
                           "finished_at": None, "error": None}
    threading.Thread(target=_run, args=(school_id, todo), daemon=True, name=f"apaar-{school_id[:8]}").start()
    return {"started": True, "students": len(todo)}


def _run(school_id: str, todo: List[Dict[str, Any]]) -> None:
    try:
        for r in todo:
            found = sdms_aadhaar.generate_apaar(school_id, r["student_id"], r["consent"])
            result = {"row": r["row"], "name": r["name"], "class": r["class"], "apaar_id": found.get("apaar_id"),
                      "error": None if found.get("ok") else found.get("error")}
            if found.get("ok"):
                plan = _read(school_id, PLAN) or {"rows": [], "done": {}}
                plan.setdefault("done", {})[str(r["student_id"])] = found["apaar_id"]
                _write(school_id, PLAN, plan)
            elif "session has ended" in str(found.get("error", "")).lower():
                with _lock:
                    JOBS[school_id]["results"].append(result)
                    JOBS[school_id].update(status="FAILED", error=found["error"], finished_at=_now())
                return
            with _lock:
                JOBS[school_id]["results"].append(result)
                JOBS[school_id]["done"] += 1
            time.sleep(1)                                      # gentle on APAAR's service
        with _lock:
            JOBS[school_id].update(status="COMPLETED", finished_at=_now())
    except Exception as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())
