"""
Updating SDMS from the filled completion sheet: upload -> validate (nothing sent) -> sync (only after the person
confirms). The sheet's rows are matched to students by PEN (the name must match too); each answer, in SDMS's words,
becomes SDMS's code again; only real changes are kept. Syncing reads each student's form from SDMS again, puts only
the changes in, saves only the tabs that changed (as SDMS's pages do) and reads it back to confirm.

Kept encrypted at data/sessions/school_<id>/: sdms_plan.json (the last validated upload) and sdms_sync_log.json
(each student's form before and after the save). Audit: student IDs and field names, never values.
"""
import hashlib
import io
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.services import secrets_box, udise_sessions
from backend.services.hpc_sessions import session_dir
from backend.services.sdms_data import load as load_students, _save as save_students
from backend.udise import client, sdms_form, sdms_write
from backend.udise.sdms import Sdms, SessionEnded

JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
DECODE = {label: (part, key, decode) for _tab, label, part, key, decode, *_ in sdms_form.REQUIRED}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _file(school_id: str, name: str) -> Path:
    return session_dir("school", school_id) / name


def _write(school_id: str, name: str, data: Any) -> None:
    path = _file(school_id, name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    for attempt in range(20):               # Windows refuses the swap while a page's poll is reading the file
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def _read(school_id: str, name: str) -> Optional[Any]:
    path = _file(school_id, name)
    for attempt in range(20):
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except PermissionError:             # being swapped by a save this moment
            time.sleep(0.05)
            continue
        try:
            return json.loads(secrets_box.decrypt(text))
        except Exception:
            return None
    return None


def _words(label: str, value: Any, masters: Dict[str, Any]) -> str:
    part, key, decode = DECODE[label]
    shown = sdms_form._cell(decode(value, masters))
    return "" if shown in (None, "") else str(shown)


# ---------------------------------------------------------------------------
# Upload and validate (nothing is sent to SDMS)
# ---------------------------------------------------------------------------

def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    """Reads a filled completion sheet: each student's changes (before -> after, in words) and the cells SDMS would
    not accept. The result is kept as the plan the next sync sends."""
    data = load_students(school_id)
    if not data:
        return {"ok": False, "error": "Fetch the students from SDMS first (it is what the sheet is checked against)."}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read. Upload the filled completion sheet (.xlsx)."}
    ws = wb["To complete"] if "To complete" in wb.sheetnames else wb.worksheets[0]
    head = [str(c.value).strip() if c.value is not None else "" for c in ws[2]]
    if "PEN" not in head or "Student's Name" not in head:
        return {"ok": False, "error": "This is not the completion sheet: its second row must have the columns PEN and "
                                      "Student's Name. Download 'Completion sheet' and fill that."}
    masters = data.get("masters") or {}
    by_pen = {str(s["general"].get("studentCodeNat") or "").strip(): s for s in data["students"]}
    students, problems_total, not_found = [], 0, []
    for r, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        cells = dict(zip(head, row))
        pen = str(cells.get("PEN") or "").strip()
        name = str(cells.get("Student's Name") or "").strip()
        if not pen and not name:
            continue
        s = by_pen.get(pen)
        if s is None:
            not_found.append(f"row {r}: PEN {pen or '(empty)'} is not one of this school's students")
            continue
        if name and name.lower() != str(s["general"].get("studentName") or "").strip().lower():
            not_found.append(f"row {r}: PEN {pen} belongs to another name on SDMS - check the row")
            continue
        changes, problems = sdms_write.changes_from_row(s, cells, masters)
        after = sdms_write.merged(s, changes)
        still = [c for c in sdms_form.completion(after, masters) if c["issue"]]
        listed = [{"tab": sdms_write.TAB_NAME[tab], "label": label, "before": _words(label, (s.get(tab) or {}).get(key), masters),
                   "after": _words(label, value, masters)}
                  for label, (tab, key, _) in sdms_write.COLUMNS.items()
                  for value in [changes.get(tab, {}).get(key, sdms_write.KEEP)] if value is not sdms_write.KEEP]
        problems_total += len(problems)
        if changes or problems or still:
            students.append({"row": r, "student_id": s["general"]["studentId"], "name": s["general"].get("studentName"),
                             "class": f"{s['general'].get('classDesc') or ''} {s['general'].get('sectionDesc') or ''}".strip(),
                             "changes": listed, "plan": changes, "problems": problems,
                             "still_missing": [f"{c['label']} ({c['issue']})" for c in still]})
    plan = {"file_name": file_name, "file_hash": hashlib.sha256(content).hexdigest(), "checked_at": _now(),
            "students": students, "not_found": not_found}
    _write(school_id, "sdms_plan.json", plan)
    return {"ok": True, **public_plan(plan)}


def public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """The plan as the page shows it (without the raw values to send)."""
    students = [{k: v for k, v in s.items() if k != "plan"} for s in plan["students"]]
    ready = [s for s in plan["students"] if s["plan"] and not s["problems"]]
    return {"file_name": plan["file_name"], "checked_at": plan["checked_at"], "students": students,
            "not_found": plan["not_found"], "ready": len(ready), "fields": sum(len(s["changes"]) for s in ready),
            "with_problems": sum(1 for s in plan["students"] if s["problems"])}


def last_plan(school_id: str) -> Optional[Dict[str, Any]]:
    plan = _read(school_id, "sdms_plan.json")
    return public_plan(plan) if plan else None


# ---------------------------------------------------------------------------
# Sync: only after the person confirms
# ---------------------------------------------------------------------------

def progress(school_id: str) -> Dict[str, Any]:
    with _lock:
        job = dict(JOBS.get(school_id) or {})
    return {"job": job or None}


def start(school_id: str, only: Optional[List[int]] = None) -> Dict[str, Any]:
    """Saves the validated plan's changes to SDMS (every student ready, or just `only` - e.g. one to try first)."""
    plan = _read(school_id, "sdms_plan.json")
    if not plan:
        return {"started": False, "error": "Upload and validate the filled sheet first."}
    todo = [s for s in plan["students"] if s["plan"] and not s["problems"] and (only is None or s["student_id"] in only)]
    if not todo:
        return {"started": False, "error": "Nothing to save: no student in the validated sheet has a change without a problem."}
    session = udise_sessions._load(school_id)
    if not (session.get("services", {}).get("sdms") or {}).get("connected"):
        return {"started": False, "error": "SDMS is not connected. Press 'Connect UDISE+' on the Home page first."}
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "A sync is already running."}
        JOBS[school_id] = {"status": "RUNNING", "done": 0, "total": len(todo), "results": [], "started_at": _now(),
                           "finished_at": None, "error": None}
    threading.Thread(target=_run, args=(school_id, session, todo), daemon=True, name=f"sdms-sync-{school_id[:8]}").start()
    return {"started": True, "students": len(todo)}


def _record(school_id: str, result: Dict[str, Any]) -> None:
    with _lock:
        job = JOBS[school_id]
        job["results"].append(result)
        job["done"] += 1


def _run(school_id: str, session: Dict[str, Any], todo: List[Dict[str, Any]]) -> None:
    from backend.services import audit
    sdms = Sdms(session)
    log = _read(school_id, "sdms_sync_log.json") or []
    data = load_students(school_id) or {"students": []}
    try:
        for s in todo:
            sid = s["student_id"]
            result = {"student_id": sid, "name": s["name"], "class": s["class"], "saved": [], "error": None}
            try:
                # what SDMS holds now (it may have changed since the fetch): the changes go on top of that
                now = {"general": sdms.student(sid), "enrolment": sdms.enrolment(sid) or {}, "facility": sdms.facility(sid) or {}}
                after = {tab: {**now[tab], **s["plan"].get(tab, {})} for tab in now}
                for tab in ("general", "enrolment", "facility"):
                    if not s["plan"].get(tab):
                        continue
                    path, body_for = sdms_write.SAVE[tab]
                    body = body_for(after[tab]) if tab == "general" else body_for(after[tab], after["general"])
                    sdms.post(path.format(id=sid), body)
                    result["saved"].append(sdms_write.TAB_NAME[tab])
                # read back: what SDMS shows now
                check = {"general": sdms.student(sid), "enrolment": sdms.enrolment(sid) or {}, "facility": sdms.facility(sid) or {}}
                not_taken = [f"{sdms_write.TAB_NAME[tab]}: {key}" for tab, keys in s["plan"].items() for key, value in keys.items()
                             if not sdms_write._same(check[tab].get(key), value)]
                if not_taken:
                    result["error"] = "Saved, but SDMS shows these unchanged: " + ", ".join(not_taken)
                log.append({"at": _now(), "student_id": sid, "before": now, "after": check})
                for entry in data["students"]:                       # the kept copy shows the new form
                    if entry["general"].get("studentId") == sid:
                        entry["general"] = {**entry["general"], **{k: v for k, v in check["general"].items() if k in entry["general"]}}
                        entry["enrolment"], entry["facility"] = check["enrolment"], check["facility"]
            except SessionEnded:
                raise
            except client.UdiseError as exc:
                result["error"] = str(exc)
            audit.record(f"school_admin:{school_id}", "sdms_save", "student", str(sid), None,
                         {"tabs": result["saved"], "fields": sorted({k for keys in s["plan"].values() for k in keys}),
                          "ok": not result["error"]})
            _record(school_id, result)
        with _lock:
            JOBS[school_id].update(status="COMPLETED", finished_at=_now())
    except SessionEnded as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=str(exc), finished_at=_now())
    except Exception as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())
    finally:
        _write(school_id, "sdms_sync_log.json", log[-500:])
        if data.get("students"):
            save_students(school_id, data)
