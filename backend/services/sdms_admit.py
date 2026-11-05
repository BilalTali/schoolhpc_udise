"""
New admissions to SDMS from the filled "New admissions" sheet: upload -> validate (nothing sent) -> add (only after
the person confirms). For a KG class or Class I, SDMS's own "Add Student" call (api/new-admission/AY, the form's
values, the AADHAAR encrypted as its page does); then the rest of the form is filled with the same saves as an update
(General, Enrolment, Other Details) and read back. SDMS's own warnings (a possible duplicate, an age that does not fit
the class) stop that row with SDMS's message - never overridden. A row added once is never sent again.
Class II and above need a reason and documents SDMS asks for there: not added from here yet.
"""
import hashlib
import io
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.services import udise_sessions
from backend.services.sdms_data import load as load_students
from backend.services.sdms_sync import _read, _write
from backend.udise import client, sdms_form, sdms_write
from backend.udise.sdms import Sdms, SessionEnded, encrypt

JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
ADD_CALL = "api/new-admission/AY"            # KG classes and Class I (SDMS uses another call from Class II)

# the sheet's columns (without " *") -> (part, key, kind) ; part "add" = the Add Student form itself
ADD_COLUMNS = {
    "Class": ("add", "class", "class"), "Section": ("add", "section", "text"),
    "Student's Name (as per School Admission Register)": ("add", "studentName", "name"),
    "Gender": ("add", "gender", "choice:gender"), "Date of Birth (DD/MM/YYYY)": ("add", "dob", "date"),
    "Mother's Name": ("add", "motherName", "name"), "Father's Name": ("add", "fatherName", "name"),
    "Guardian's Name": ("add", "guardianName", "name"),
    "AADHAAR Number of Student (12 digits)": ("add", "uuid", "aadhaar"),
    "Name of Student as per AADHAAR": ("add", "nameAsUuid", "name"),
    "Admission Date in Present School (DD/MM/YYYY)": ("add", "admnStartDate", "date"),
    "State Student Code": ("add", "studentCodeState", "code"), "Mobile Number (10 digits)": ("add", "primaryMobile", "mobile"),
    "Alternate Mobile Number": ("add", "secondaryMobile", "mobile"), "Whether CWSN?": ("add", "cwsnYN", "choice:yes_no"),
    "Address (10 to 150 characters)": ("general", "address", "text"), "Pincode (6 digits)": ("general", "pincode", "int"),
    "Mother Tongue": ("general", "motherTongue", "list:mother_tongue"), "Social Category": ("general", "socCatId", "choice:social"),
    "Minority Group": ("general", "minorityId", "choice:minority"), "Whether BPL beneficiary?": ("general", "isBplYN", "choice:yes_no"),
    "Whether AAY beneficiary?": ("general", "aayBplYN", "choice:yes_no"),
    "Whether EWS / Disadvantaged Group?": ("general", "ewsYN", "choice:yes_no"),
    "Type of impairment (if CWSN)": ("general", "impairmentType", "codes"),
    "Disability Percentage (if CWSN)": ("general", "impairmentPercent", "number"),
    "Whether Indian National?": ("general", "natIndYN", "choice:yes_no"), "Out-of-School-Child?": ("general", "ooscYN", "choice:yes_no"),
    "Mainstreamed?": ("general", "ooscMainstreamedYN", "choice:yes_no"),
    "Admission Number in Present School": ("enrolment", "admnNumber", "text"),
    "Status in Previous Academic Year": ("enrolment", "enrStatusPY", "choice:status_py"),
    "Class Studied in Previous Year (if studied)": ("enrolment", "classPY", "class"),
    "Previous Class - Result (if studied)": ("enrolment", "examResultPy", "choice:exam_result"),
    "Previous Class - Marks % (if studied)": ("enrolment", "examMarksPy", "number"),
    "Days Attended last year (if studied)": ("enrolment", "attendancePy", "int"),
    "Medium of Instruction": ("enrolment", "moiId", "list:moi"),
    "Facilities provided?": ("facility", "facilityYn", "choice:yes_no"),
    "Which facilities (comma separated)": ("facility", "facProvided", "facilities"),
    "Olympiads / Competitions?": ("facility", "olympdsNlc", "choice:yes_no"), "NCC": ("facility", "nccYn", "choice:yes_no"),
    "NSS": ("facility", "nssYn", "choice:yes_no"), "Scouts and Guides": ("facility", "scoutsYn", "choice:yes_no"),
    "Height (cm)": ("facility", "heightInCm", "int"), "Weight (kg)": ("facility", "weightInKg", "int"),
    "Distance to School": ("facility", "distanceFrmSchool", "choice:distance"),
    "Parents' Highest Education": ("facility", "parentEducation", "choice:parent_education"),
}
REQUIRED = {label.replace(" *", "") for label, required, _ in sdms_form.ADD_STUDENT + sdms_form.REST_OF_FORM if required}
NAME = re.compile(r"^[a-zA-Z.']+( [a-zA-Z.']+)*$")


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _check(kind: str, cell: Any, masters: Dict[str, Any]):
    """(value, problem) for one cell of the sheet."""
    text = "" if cell is None else str(cell).strip()
    if kind == "name":
        return (text, None) if NAME.match(text) and len(text) <= 100 else (None, "letters, spaces, . and ' only (up to 100)")
    if kind == "aadhaar":
        digits = text.replace(" ", "")
        return (digits, None) if digits.isdigit() and len(digits) == 12 and digits[0] not in "01" else (None, "12 digits, not starting with 0 or 1")
    if kind == "mobile":
        return (text, None) if text.isdigit() and len(text) == 10 and text[0] in "6789" else (None, "10 digits starting with 6, 7, 8 or 9")
    if kind == "code":
        return (text, None) if re.match(r"^[a-zA-Z0-9]{1,25}$", text) else (None, "letters and digits only (up to 25)")
    value, problem = sdms_write.to_value(kind, cell, masters)
    return (None if value is sdms_write.KEEP else value), problem


def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    data = load_students(school_id)
    if not data:
        return {"ok": False, "error": "Fetch the students from SDMS first (the sheet is checked against them)."}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read. Upload the filled New admissions sheet (.xlsx)."}
    if "New students" not in wb.sheetnames:
        return {"ok": False, "error": "This is not the New admissions sheet (its sheet 'New students' is missing). "
                                      "Download 'New admissions sheet' and fill that."}
    ws = wb["New students"]
    head = [str(c.value).replace(" *", "").strip() if c.value is not None else "" for c in ws[3]]
    masters = data.get("masters") or {}
    classes = {str(c.get("classDesc")).strip().lower(): c.get("classId") for c in data["classes"]}
    sections = {}                                         # (classId, section letter) -> sectionId, from SDMS's students
    for s in data["students"]:
        g = s["general"]
        sections[(g.get("classId"), str(g.get("sectionDesc") or "").strip().upper())] = g.get("sectionId")
    known = {(str(s["general"].get("studentName") or "").strip().lower(), str(s["general"].get("fatherName") or "").strip().lower(),
              str(s["general"].get("dob") or "")) for s in data["students"]}
    old = _read(school_id, "sdms_admit_plan.json") or {}
    added = old.get("added", {})                          # row fingerprint -> new student id (never sent twice)
    rows = []
    for r, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        cells = {h: v for h, v in zip(head, row) if h}
        if not any(v not in (None, "") for v in cells.values()):
            continue
        add, rest, problems = {}, {"general": {}, "enrolment": {}, "facility": {}}, []
        for label, (part, key, kind) in ADD_COLUMNS.items():
            cell = cells.get(label)
            if cell in (None, "") or str(cell).strip() == "":
                if label in REQUIRED:
                    problems.append(f"{label}: required")
                continue
            if kind == "class":
                value = classes.get(str(cell).strip().lower())
                problem = None if value is not None else "a class of this school (use the drop-down)"
            else:
                value, problem = _check(kind, cell, masters)
            if problem:
                problems.append(f"{label}: {problem}")
            elif value is not None:
                (add if part == "add" else rest[part])[key] = value
        class_id = add.get("class")
        if class_id is not None:
            add["sectionId"] = sections.get((class_id, str(add.get("section") or "").strip().upper()))
            if add["sectionId"] is None:
                problems.append(f"Section: '{add.get('section')}' is not a section of this class on SDMS")
            if class_id >= 2:
                problems.append("Class II and above: add on SDMS for now (it also asks for a reason and the documents given)")
        if (str(add.get("studentName", "")).lower(), str(add.get("fatherName", "")).lower(), str(add.get("dob", ""))) in known:
            problems.append("A student with this name, father's name and date of birth is already on SDMS")
        fingerprint = hashlib.sha256(f"{add.get('studentName')}|{add.get('fatherName')}|{add.get('dob')}|{add.get('uuid')}".encode()).hexdigest()
        rows.append({"row": r, "name": add.get("studentName") or "(no name)", "class": f"{cells.get('Class') or ''} {add.get('section') or ''}".strip(),
                     "problems": problems, "add": add, "rest": rest, "fingerprint": fingerprint,
                     "added_as": added.get(fingerprint)})
    plan = {"file_name": file_name, "checked_at": _now(), "rows": rows, "added": added}
    _write(school_id, "sdms_admit_plan.json", plan)
    return {"ok": True, **public(plan)}


def public(plan: Dict[str, Any]) -> Dict[str, Any]:
    """What the page shows: no AADHAAR, no raw values."""
    rows = [{"row": r["row"], "name": r["name"], "class": r["class"], "problems": r["problems"], "added_as": r.get("added_as")}
            for r in plan["rows"]]
    ready = [r for r in plan["rows"] if not r["problems"] and not r.get("added_as")]
    return {"file_name": plan["file_name"], "checked_at": plan["checked_at"], "rows": rows, "ready": len(ready),
            "with_problems": sum(1 for r in plan["rows"] if r["problems"]),
            "already_added": sum(1 for r in plan["rows"] if r.get("added_as"))}


def last_plan(school_id: str) -> Optional[Dict[str, Any]]:
    plan = _read(school_id, "sdms_admit_plan.json")
    return public(plan) if plan and plan.get("rows") is not None else None


def progress(school_id: str) -> Dict[str, Any]:
    with _lock:
        return {"job": dict(JOBS.get(school_id) or {}) or None}


def start(school_id: str, only_rows: Optional[List[int]] = None) -> Dict[str, Any]:
    plan = _read(school_id, "sdms_admit_plan.json")
    if not plan or plan.get("rows") is None:
        return {"started": False, "error": "Upload and check the filled New admissions sheet first."}
    todo = [r for r in plan["rows"] if not r["problems"] and not r.get("added_as") and (only_rows is None or r["row"] in only_rows)]
    if not todo:
        return {"started": False, "error": "Nothing to add: every row has something to correct, or was added already."}
    session = udise_sessions._load(school_id)
    if not (session.get("services", {}).get("sdms") or {}).get("connected"):
        return {"started": False, "error": udise_sessions.sdms_not_connected(school_id)}
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "Adding is already running."}
        JOBS[school_id] = {"status": "RUNNING", "done": 0, "total": len(todo), "results": [], "started_at": _now(),
                           "finished_at": None, "error": None}
    threading.Thread(target=_run, args=(school_id, session, todo), daemon=True, name=f"sdms-admit-{school_id[:8]}").start()
    return {"started": True, "students": len(todo)}


def add_body(add: Dict[str, Any], school_id_sdms: int, key: str) -> Dict[str, Any]:
    """basicDetailsForm's raw value as SDMS's page sends it (dates DD/MM/YYYY, the AADHAAR encrypted)."""
    return {"classId": add["class"], "schoolId": school_id_sdms, "sectionId": add["sectionId"],
            "studentName": add["studentName"], "gender": add["gender"], "dob": add["dob"],
            "motherName": add["motherName"], "fatherName": add["fatherName"], "guardianName": add.get("guardianName", ""),
            "uuid": encrypt(add["uuid"], key), "nameAsUuid": add["nameAsUuid"], "admnStartDate": add["admnStartDate"],
            "studentCodeState": add.get("studentCodeState", ""), "primaryMobile": add["primaryMobile"],
            "secondaryMobile": add.get("secondaryMobile", ""), "cwsnYN": add["cwsnYN"],
            "ageCheckSkipped": 2, "skipDuplicate": 2}


def _refused(answer: Dict[str, Any]) -> str:
    """SDMS's reason, in its words; a duplicate or an age warning is for the person to decide on SDMS."""
    error = answer.get("error") or {}
    kind = error.get("type") if isinstance(error, dict) else None
    message = (error.get("message") if isinstance(error, dict) else None) or answer.get("message") or "SDMS did not add the student."
    if kind in ("error_duplicate_student", "ALERT", "error_duplicate_student_name_mobile", "error_duplicate_student_mobile_maximum_use"):
        return f"SDMS says this may be a student already on SDMS: {message} - check on SDMS (not added)."
    if isinstance(error, dict) and ((error.get("data") or {}).get("additionalParams") or {}).get("ageCheckAlert"):
        return f"SDMS says the age does not fit the class: {message} - add this student on SDMS, confirming the age there (not added)."
    fields = (error.get("data") or {}).get("errorFields") if isinstance(error, dict) else None
    return f"SDMS did not add the student: {message}" + (f" ({fields})" if fields else "")


def _run(school_id: str, session: Dict[str, Any], todo: List[Dict[str, Any]]) -> None:
    from backend.services import audit
    sdms = Sdms(session)
    plan = _read(school_id, "sdms_admit_plan.json") or {"rows": [], "added": {}}
    try:
        school = sdms.school_id()
        key = sdms.key()
        for r in todo:
            result = {"row": r["row"], "name": r["name"], "class": r["class"], "student_id": None, "filled": [], "error": None}
            try:
                answer = sdms.post_answer(ADD_CALL, add_body(r["add"], school, key))
                if answer.get("status") is not True or not (answer.get("data") or {}).get("studentId"):
                    result["error"] = _refused(answer)
                else:
                    sid = answer["data"]["studentId"]
                    result["student_id"] = sid
                    plan.setdefault("added", {})[r["fingerprint"]] = sid          # never sent again
                    _write(school_id, "sdms_admit_plan.json", plan)
                    now = {"general": sdms.student(sid), "enrolment": sdms.enrolment(sid) or {}, "facility": sdms.facility(sid) or {}}
                    for tab in ("general", "enrolment", "facility"):
                        if not r["rest"].get(tab):
                            continue
                        merged = {**now[tab], **r["rest"][tab]}
                        path, body_for = sdms_write.SAVE[tab]
                        body = body_for(merged) if tab == "general" else body_for(merged, {**now["general"], **r["rest"]["general"]})
                        try:
                            sdms.post(path.format(id=sid), body)
                            result["filled"].append(sdms_write.TAB_NAME[tab])
                        except client.UdiseError as exc:
                            result["error"] = f"Added (ID {sid}); {sdms_write.TAB_NAME[tab]} not saved: {exc}. Fill it on SDMS or with the completion sheet."
                            break
            except SessionEnded:
                raise
            except client.UdiseError as exc:
                result["error"] = str(exc)
            audit.record(f"school_admin:{school_id}", "sdms_admit", "student", str(result["student_id"] or f"row {r['row']}"),
                         None, {"added": bool(result["student_id"]), "filled": result["filled"], "ok": not result["error"]})
            with _lock:
                JOBS[school_id]["results"].append(result)
                JOBS[school_id]["done"] += 1
        with _lock:
            JOBS[school_id].update(status="COMPLETED", finished_at=_now())
    except SessionEnded as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=str(exc), finished_at=_now())
    except Exception as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())
