"""
Updating SDMS from the filled completion sheet or All details workbook: upload -> validate (nothing sent) -> sync (only after the person
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
_lock = threading.RLock()
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


# ---------------------------------------------------------------------------
# Upload and validate (nothing is sent to SDMS)
# ---------------------------------------------------------------------------

PEN_COLUMNS = ("PEN", "PEN (Student code)")
NAME_COLUMNS = ("Student's Name", "Student's Name (as per School record/School Admission Register)")


def _sheets(wb) -> List[Any]:
    """The sheets with students: row 2 has a PEN and a name column (the completion sheet, or the All details
    workbook's 'All students' and class sheets)."""
    found = []
    for ws in wb.worksheets:
        head = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=2, max_row=2), [])]
        pen = next((h for h in PEN_COLUMNS if h in head), None)
        name = next((h for h in NAME_COLUMNS if h in head), None)
        if pen and name:
            found.append((ws, head, pen, name))
    return found


def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    """Reads a filled completion sheet or All details workbook: each student's changes (before -> after, in words)
    and the cells SDMS would not accept. Only cells that differ from what SDMS holds are read. The result is kept
    as the plan the next sync sends."""
    data = load_students(school_id)
    if not data:
        return {"ok": False, "error": "Fetch the students from SDMS first (it is what the sheet is checked against)."}
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read. Upload the completion sheet or the "
                                      "All details workbook (.xlsx)."}
    sheets = _sheets(wb)
    if not sheets:
        return {"ok": False, "error": "This is not one of the app's SDMS sheets: its second row must have the PEN and the "
                                      "student's name. Download 'All details in Excel' or the completion sheet and fill that."}
    masters = data.get("masters") or {}
    by_pen = {str(s["general"].get("studentCodeNat") or "").strip(): s for s in data["students"]}
    found: Dict[Any, Dict[str, Any]] = {}          # student id -> rows read, changes, where each change came from
    not_found: List[str] = []
    for ws, head, pen_col, name_col in sheets:
        labels = sdms_write.COLUMNS if "Student's Name" in head else sdms_write.FULL_COLUMNS
        for r, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            cells = dict(zip(head, row))
            pen = sdms_write._text(cells.get(pen_col)).upper()
            name = str(cells.get(name_col) or "").strip()
            if not pen and not name:
                continue
            where = f"'{ws.title}' row {r}"
            s = by_pen.get(pen) or next((v for k, v in by_pen.items() if k.upper() == pen), None)
            if s is None:
                not_found.append(f"{where}: PEN {pen or '(empty)'} is not one of this school's students")
                continue
            if name and name.lower() != str(s["general"].get("studentName") or "").strip().lower():
                not_found.append(f"{where}: PEN {pen} belongs to another name on SDMS - check the row "
                                 "(a name is changed on SDMS itself)")
                continue
            entry = found.setdefault(s["general"]["studentId"], {"student": s, "row": r, "sheet": ws.title, "plan": {},
                                                                 "labels": {}, "from": {}, "problems": [], "ignored": []})
            changes, problems = sdms_write.changes_from_row(s, cells, masters, labels)
            entry["problems"] += [f"{p} ({where})" if len(sheets) > 1 else p for p in problems]
            for tab, keys in changes.items():
                for key, value in keys.items():
                    label = next(l for l, (t, k, _) in labels.items() if (t, k) == (tab, key))
                    before = entry["plan"].get(tab, {}).get(key, sdms_write.KEEP)
                    if before is not sdms_write.KEEP and not sdms_write._same(before, value):
                        entry["problems"].append(f"{label}: changed differently in {entry['from'][(tab, key)]} and {where}")
                        continue
                    entry["plan"].setdefault(tab, {})[key] = value
                    entry["labels"][(tab, key)] = label
                    entry["from"][(tab, key)] = where
                    if not entry.get("edited"):
                        entry.update(edited=True, row=r, sheet=ws.title)
            if labels is sdms_write.FULL_COLUMNS:
                for label in sdms_write.READ_ONLY:
                    if label not in cells:
                        continue
                    part, key, _ = sdms_write.FORM_FIELDS[label]
                    now = sdms_write.shown(part, key, (s.get(part) or {}).get(key), masters)
                    if sdms_write._text(cells[label]) != sdms_write._text(now) and label not in entry["ignored"]:
                        entry["ignored"].append(label)
    students, problems_total = [], 0
    for sid, e in found.items():
        s, changes = e["student"], e["plan"]
        after = sdms_write.merged(s, changes)
        still = [c for c in sdms_form.completion(after, masters) if c["issue"]]
        listed = [{"tab": sdms_write.TAB_NAME[tab], "label": e["labels"][(tab, key)],
                   "before": sdms_write.shown(tab, key, (s.get(tab) or {}).get(key), masters),
                   "after": sdms_write.shown(tab, key, value, masters), "cell": e["from"][(tab, key)]}
                  for tab, keys in changes.items() for key, value in keys.items()]
        problems_total += len(e["problems"])
        if changes or e["problems"] or e["ignored"] or still:
            students.append({"row": e["row"], "sheet": e["sheet"], "student_id": sid, "name": s["general"].get("studentName"),
                             "class": f"{s['general'].get('classDesc') or ''} {s['general'].get('sectionDesc') or ''}".strip(),
                             "changes": listed, "plan": changes, "problems": e["problems"], "ignored": e["ignored"],
                             "still_missing": [f"{c['label']} ({c['issue']})" for c in still]})
    students.sort(key=lambda x: (not x["changes"], not x["problems"], x["class"], str(x["name"] or "")))
    plan = {"file_name": file_name, "file_hash": hashlib.sha256(content).hexdigest(), "checked_at": _now(),
            "students": students, "not_found": not_found}
    _write(school_id, "sdms_plan.json", plan)
    return {"ok": True, **public_plan(plan, school_id)}


def already_saved(school_id: str, plan: Dict[str, Any]) -> set:
    """The students whose planned changes SDMS already holds (the app's copy, updated after each save): they are
    never counted as ready or sent again."""
    data = load_students(school_id) or {"students": []}
    kept = {s["general"].get("studentId"): s for s in data["students"]}
    done = set()
    for s in plan["students"]:
        entry = kept.get(s["student_id"])
        if entry and s["plan"] and all(sdms_write._same((entry.get(tab) or {}).get(key), value)
                                       for tab, keys in s["plan"].items() for key, value in keys.items()):
            done.add(s["student_id"])
    return done


def public_plan(plan: Dict[str, Any], school_id: Optional[str] = None) -> Dict[str, Any]:
    """The plan as the page shows it (without the raw values to send). With school_id, students whose changes SDMS
    already has are marked done and not counted as ready."""
    done = already_saved(school_id, plan) if school_id else set()
    students = [{**{k: v for k, v in s.items() if k != "plan"}, "done": s["student_id"] in done} for s in plan["students"]]
    ready = [s for s in plan["students"] if s["plan"] and not s["problems"] and s["student_id"] not in done]
    return {"file_name": plan["file_name"], "checked_at": plan["checked_at"], "students": students,
            "not_found": plan["not_found"], "ready": len(ready), "fields": sum(len(s["changes"]) for s in ready),
            "already_saved": len(done), "with_problems": sum(1 for s in plan["students"] if s["problems"])}


def last_plan(school_id: str) -> Optional[Dict[str, Any]]:
    plan = _read(school_id, "sdms_plan.json")
    return public_plan(plan, school_id) if plan else None


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
    done = already_saved(school_id, plan)
    todo = [s for s in plan["students"] if s["plan"] and not s["problems"] and s["student_id"] not in done
            and (only is None or s["student_id"] in only)]
    if not todo:
        return {"started": False, "error": "Nothing to save: every student's change is already on SDMS, or has a problem to fix."}
    session = udise_sessions._load(school_id)
    if not (session.get("services", {}).get("sdms") or {}).get("connected"):
        return {"started": False, "error": udise_sessions.sdms_not_connected(school_id)}
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
            if not ((udise_sessions._load(school_id).get("services") or {}).get("sdms") or {}).get("connected"):
                raise SessionEnded("Stopped: UDISE+ was disconnected. The students saved so far stay saved; connect "
                                   "again and press Save to send the rest.")
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
                save_students(school_id, data)                      # kept at once: a stop or restart loses nothing
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
