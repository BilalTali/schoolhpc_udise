"""
UDISE+ Teacher module for the current session, with an Excel workbook: one row per staff member, the yearly forms
as columns (Form 1 general profile, Form 2 appointment, Form 3 training), and a sheet for new staff.

start()/progress()  reads every staff member's forms from UDISE+ in the background (about 2 calls a second);
                    the read is kept (encrypted) for the page, the workbook and the report
status()            exactly where each staff member stands: every field still needed, with its place in the
                    workbook (sheet, row, column), and what the app updated (the history)
excel()             the workbook
validate()          a filled workbook -> the changes per staff member, new staff, problems. Sends nothing.
save()              saves them, staff by staff, form by form: re-read first, a copy kept, only edited fields changed.
                    SAVE_ENABLED stays False until the answers of the Teacher service have been checked against a
                    real school's data (field formats and lists); until then the page says so and nothing is sent.
Certifying stays on the UDISE+ website.
"""
import copy
import io
import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DATA_DIR
from backend.hpc.xl import grid_sheets, keep_text
from backend.services import secrets_box, udise_sessions
from backend.services.hpc_sessions import session_dir
from backend.services.safe_paths import inside
from backend.udise import bearer, client
from backend.udise import teacher_forms as tf

SAVE_ENABLED = False
WORKBOOK_KIND = "udise_teacher_v1"
FIRST_ROW = 5
JOBS: Dict[str, Dict[str, Any]] = {}
_LOCKS: Dict[str, threading.Lock] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _service(school_id: str) -> bearer.Service:
    return bearer.Service(school_id, "teacher", udise_sessions.load_saved(school_id))


def _file(school_id: str, name: str):
    return session_dir("school", school_id) / name


def _write(school_id: str, name: str, data: Any) -> None:
    path = _file(school_id, name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    tmp.replace(path)


def _read(school_id: str, name: str) -> Optional[Any]:
    path = _file(school_id, name)
    if not path.exists():
        return None
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:
        return None


# ---------------------------------------------------------------- reading (background)

def _name(row: Dict[str, Any]) -> str:
    return str(next((row[k] for k in ("empName", "teacherName", "staffName", "name", "employeeName") if row.get(k)), ""))


def _natcode(row: Dict[str, Any]) -> str:
    return str(next((row[k] for k in ("nationalCode", "natTchId", "natCode", "nationalId") if row.get(k)), ""))


def _staff_list(answer: Any) -> List[Dict[str, Any]]:
    if isinstance(answer, dict):
        for k in ("teacherDetails", "data", "staffList", "body"):
            if isinstance(answer.get(k), list):
                return answer[k]
    return answer if isinstance(answer, list) else []


def _lists(svc: bearer.Service, state: Any, staff: List[Dict[str, Any]]) -> Dict[str, Dict[int, str]]:
    """The code lists the forms use, read once."""
    out: Dict[str, Dict[int, str]] = {}

    def take(path: str, params=None) -> Any:
        try:
            return svc.get(path, params)
        except bearer.Refused:
            return None

    for staff_type in tf.STAFF_TYPES:
        found = take(f"/teacher/dropdown/all/{staff_type}/{state}")
        if isinstance(found, dict):
            for k, v in found.items():
                if isinstance(v, list) and tf.as_options(v):
                    out.setdefault(k, {}).update(tf.as_options(v))
    if out.get("genders"):
        out["gender"] = out["genders"]
    out["socialCategory"] = tf.as_options(take("/teacher/masterdata/social-category"))
    out["training"] = tf.as_options(take("/teacher/dropdown/training-received"))
    out["languages"] = tf.as_options(take(f"/teacher/masterdata/languages/{state}"))
    first = next((s for s in staff if s["type"] == 1), None)
    if first:
        found = take("/teacher/dropdown/appointment-teaching-dropdowns",
                     {"schoolId": svc.region_id, "empStaffId": first["id"]})
        if isinstance(found, dict):
            for k, v in found.items():
                if isinstance(v, list) and tf.as_options(v):
                    out.setdefault(k, {}).update(tf.as_options(v))
    subjects: Dict[int, str] = {}
    for cls in sorted({s["forms"].get("2", {}).get("classTaught") for s in staff if s["type"] == 1} - {None, "", 0}):
        subjects.update(tf.as_options(take("/teacher/dropdown/by-class-and-state", {"classTaught": cls, "stateId": state})))
    out["subjects"] = subjects
    return out


def start(school_id: str) -> Dict[str, Any]:
    job = JOBS.get(school_id)
    if job and job["status"] == "RUNNING":
        return {"started": False, "error": "Already reading the staff from UDISE+."}
    try:
        svc = _service(school_id)
    except bearer.SessionEnded as exc:
        return {"started": False, "error": str(exc)}
    JOBS[school_id] = {"status": "RUNNING", "step": "Reading the staff lists", "done": 0, "total": 0, "error": None}
    threading.Thread(target=_run, args=(school_id, svc), daemon=True).start()
    return {"started": True}


def progress(school_id: str) -> Dict[str, Any]:
    saved = _read(school_id, "udise_teacher.json")
    return {"job": JOBS.get(school_id), "saved": {"read_at": saved["read_at"], "staff": len(saved["staff"])} if saved else None}


def _run(school_id: str, svc: bearer.Service) -> None:
    job = JOBS[school_id]
    try:
        sid, state = svc.region_id, svc.token.get("userStateId")
        staff = []
        for staff_type, label in tf.STAFF_TYPES.items():
            job["step"] = f"Reading the list: {label}"
            for row in _staff_list(svc.get(f"/teacher/emp-staff/teacher-details/{sid}/{staff_type}")):
                emp = row.get("empStaffId") or row.get("id")
                if emp is not None:
                    staff.append({"id": emp, "type": staff_type, "name": _name(row), "national_code": _natcode(row),
                                  "form_flag": row.get("formFlag"), "list_row": row, "forms": {}, "errors": {}})
        job.update(step="Reading each staff member's forms", total=len(staff))
        for s in staff:
            for form, (read, _) in tf.paths(s["type"], sid, s["id"]).items():
                try:
                    s["forms"][form] = svc.get(read) or {}
                except bearer.Refused as exc:
                    s["errors"][form] = str(exc)
            s["name"] = s["name"] or _name(s["forms"].get("1", {}))
            job["done"] += 1
        job["step"] = "Reading the lists of codes"
        lists = _lists(svc, state, staff)
        try:
            school = svc.get(f"/teacher/school/dashboard/basicSchool-info/{sid}") or {}
        except bearer.Refused:
            school = {}
        _write(school_id, "udise_teacher.json", {"read_at": _now(), "school_id": sid, "state_id": state, "school": school,
                                                 "staff": staff, "lists": {k: {str(c): w for c, w in v.items()} for k, v in lists.items()}})
        job.update(status="COMPLETED", step="Done")
    except client.UdiseError as exc:
        job.update(status="FAILED", error=str(exc))
    except Exception as exc:                                          # never leave the page waiting
        job.update(status="FAILED", error=f"Reading stopped: {type(exc).__name__}")


def load(school_id: str) -> Optional[Dict[str, Any]]:
    data = _read(school_id, "udise_teacher.json")
    if data:
        data["lists"] = {k: {int(c): w for c, w in v.items()} for k, v in (data.get("lists") or {}).items()}
    return data


# ---------------------------------------------------------------- values in words and back

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DMY = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def _blank(kind: str, v: Any) -> bool:
    if v is None or (isinstance(v, str) and not v.strip()) or str(v).strip().lower() in ("null", "none"):
        return True
    return (kind == "yn" or kind.startswith("list:")) and str(v).strip() in ("0", "9", "-1")


def show(kind: str, v: Any, lists: Dict[str, Dict[int, str]]) -> Any:
    if _blank(kind, v):
        return None
    if kind == "date":
        m = _ISO.match(str(v))
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(v)
    opts = tf.options_of(kind, lists)
    if kind == "yn" or kind.startswith("list:"):
        try:
            code = int(v)
        except (TypeError, ValueError):
            return str(v)
        return f"{code} - {opts[code]}" if code in opts else str(code)
    if kind == "num":
        try:
            return int(v)
        except (TypeError, ValueError):
            return v
    return str(v)


def allowed(kind: str, lists: Dict[str, Dict[int, str]]) -> str:
    opts = tf.options_of(kind, lists)
    if kind == "yn" or kind.startswith("list:"):
        return ", ".join(f"{c} - {w}" for c, w in opts.items())[:250] or "the code from UDISE+"
    return {"date": "DD/MM/YYYY", "num": "whole number", "year": "e.g. 2019", "mobile": "10 digits, starting 6-9",
            "email": "name@example.com", "aadhaar": "12 digits", "text": "words"}.get(kind, "")


def parse(kind: str, cell: Any, lists: Dict[str, Dict[int, str]], like: Any = None) -> Tuple[Any, Optional[str]]:
    """A cell -> (value UDISE+ stores, problem). Empty: (None, None), left as it is. Dates are sent in the style
    UDISE+ answered with ('like'): YYYY-MM-DD or DD/MM/YYYY."""
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None, None
    if isinstance(cell, datetime):
        cell = cell.strftime("%d/%m/%Y")
    text = str(cell).strip()
    if kind == "yn" or kind.startswith("list:"):
        opts = tf.options_of(kind, lists)
        m = re.match(r"^\s*(-?\d+)\b", text)
        code = int(m.group(1)) if m else next((c for c, w in opts.items() if w.lower() == text.lower()), None)
        if code is None or (opts and code not in opts):
            return None, f"'{text}' is not one of the allowed answers."
        return code, None
    if kind == "date":
        m = _DMY.match(text)
        iso = _ISO.match(text)
        if iso:
            d, mo, y = iso.group(3), iso.group(2), iso.group(1)
        elif m:
            d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        else:
            return None, f"'{text}' is not a date like 25/06/2015."
        try:
            when = datetime(int(y), int(mo), int(d))
        except ValueError:
            return None, f"'{text}' is not a real date."
        if when > datetime.now():
            return None, "The date is in the future."
        return (f"{y}-{mo}-{d}" if like and _ISO.match(str(like)) else f"{d}/{mo}/{y}"), None
    if kind == "num":
        if not re.fullmatch(r"\d+(\.0)?", text):
            return None, f"'{text}' should be a whole number."
        return int(float(text)), None
    if kind == "year":
        if not re.fullmatch(r"(19|20)\d{2}(\.0)?", text) or int(float(text)) > datetime.now().year:
            return None, f"'{text}' is not a past year like 2019."
        return str(int(float(text))), None
    if kind == "mobile":
        digits = re.sub(r"\D", "", text)
        if not re.fullmatch(r"[6-9]\d{9}", digits) or len(set(digits)) == 1:
            return None, "A mobile number has 10 digits and starts with 6, 7, 8 or 9."
        return digits, None
    if kind == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
            return None, f"'{text}' is not an email address."
        return text, None
    if kind == "aadhaar":
        digits = re.sub(r"\D", "", text)
        if len(digits) != 12 or len(set(digits)) == 1:
            return None, "The Aadhaar number has 12 digits."
        return digits, None
    return text, None


def _name_ok(key: str, value: Any) -> Optional[str]:
    """The page's rule for the two names: letters, spaces, dots and apostrophes."""
    if key in ("empName", "empNamePerUid") and value is not None and not re.fullmatch(r"[A-Za-z .']{2,}", str(value)):
        return "only letters, spaces, dots and apostrophes."
    return None


def _same(a: Any, b: Any) -> bool:
    if _blank("text", a) and _blank("text", b):
        return True
    return str(a).strip().lower() == str(b).strip().lower()


def _value(staff: Dict[str, Any], form: str, key: str) -> Any:
    data = staff["forms"].get(form) or {}
    if key == "postId" and staff["type"] == 4 and "postId" not in data:
        return data.get("currentPostHeld")
    return data.get(key)


# ---------------------------------------------------------------- where each staff member stands

def _sheet(staff_type: int) -> str:
    return tf.STAFF_TYPES[staff_type][:31]


def _letter(n: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(n)


VISIBLE_FIRST = 3          # columns A, B, C: national code, name, form status; the fields start at D


def _asked(staff: Dict[str, Any], key: str) -> bool:
    rule = tf.WHEN.get(key)
    if key in tf.OPTIONAL:
        return False
    if rule:
        form = next(f for f, k, _, _ in tf.columns(staff["type"]) if k == rule[0])
        try:
            return int(_value(staff, form, rule[0])) in rule[1]
        except (TypeError, ValueError):
            return False
    return True


def status(school_id: str) -> Optional[Dict[str, Any]]:
    data = load(school_id)
    if not data:
        return None
    lists = data["lists"]
    groups, needed = [], []
    for staff_type, label in tf.STAFF_TYPES.items():
        people = [s for s in data["staff"] if s["type"] == staff_type]
        cols = tf.columns(staff_type)
        complete = 0
        for n, s in enumerate(people):
            missing = []
            for i, (form, key, field_label, kind) in enumerate(cols):
                if form in s["errors"] or not _asked(s, key):
                    continue
                if _blank(kind, _value(s, form, key)):
                    missing.append(field_label)
                    needed.append({"type": label, "staff": s["name"], "national_code": s["national_code"], "form": f"Form {form}",
                                   "field": field_label, "sheet": _sheet(staff_type), "row": FIRST_ROW + n,
                                   "column": _letter(VISIBLE_FIRST + 1 + i), "allowed": allowed(kind, lists)})
            s_done = str(s.get("form_flag")) == "3"
            complete += 1 if s_done and not missing else 0
            s["_missing"] = missing
        groups.append({"type": staff_type, "label": label, "staff": len(people), "complete": complete,
                       "people": [{"name": s["name"], "national_code": s["national_code"], "form_flag": s.get("form_flag"),
                                   "complete_on_udise": str(s.get("form_flag")) == "3", "missing": s["_missing"],
                                   "errors": s["errors"], "row": FIRST_ROW + i} for i, s in enumerate(people)]})
    return {"read_at": data["read_at"], "groups": groups, "needed": needed, "updated": load_history(school_id),
            "school": data.get("school") or {}, "save_enabled": SAVE_ENABLED}


def load_history(school_id: str) -> List[Dict[str, Any]]:
    return _read(school_id, "udise_teacher_history.json") or []


def _add_history(school_id: str, entries: List[Dict[str, Any]]) -> None:
    if entries:
        _write(school_id, "udise_teacher_history.json", (load_history(school_id) + entries)[-5000:])


# ---------------------------------------------------------------- the workbook

def excel(school_id: str) -> Optional[Tuple[bytes, str]]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.worksheet.datavalidation import DataValidation

    data = load(school_id)
    if not data:
        return None
    lists = data["lists"]
    blue, white, bold = PatternFill("solid", fgColor="0B5FA5"), Font(bold=True, color="FFFFFF"), Font(bold=True)
    answer_fill, needed_fill = PatternFill("solid", fgColor="FFF7D6"), PatternFill("solid", fgColor="FDE2E2")
    form_fill = {"1": PatternFill("solid", fgColor="334155"), "2": PatternFill("solid", fgColor="0B5FA5"),
                 "3": PatternFill("solid", fgColor="046A38")}
    wrap = Alignment(wrap_text=True, vertical="top")
    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    school = data.get("school") or {}
    for text, font in [
        ("UDISE+ Teacher module - staff details", Font(bold=True, size=14)),
        (f"{school.get('schoolName') or ''} {school.get('udiseCode') or ''}".strip(), bold),
        (f"Read from UDISE+ {data['read_at'][:16].replace('T', ' ')} UTC.", None), ("", None),
        ("1. One sheet per kind of staff, one row per person; the columns are Form 1 (general), Form 2 (appointment) "
         "and Form 3 (training).", None),
        ("2. Change the yellow cells. Pink cells are still empty on UDISE+ and needed. Pick from the list or type the code.", None),
        ("3. Dates as DD/MM/YYYY. An empty cell is left as it is on UDISE+.", None),
        ("4. New staff: fill a row on the 'New staff' sheet (Aadhaar and name as per Aadhaar are needed).", None),
        ("5. Upload the file in the app: the changes are shown before anything is sent. Certify on the UDISE+ website.", None),
    ]:
        readme.append([text])
        if font:
            readme.cell(row=readme.max_row, column=1).font = font
    readme.column_dimensions["A"].width = 110
    lists_ws = wb.create_sheet("Lists")
    ranges: Dict[str, str] = {}
    meta_ws = wb.create_sheet("_meta")

    def validation(ws, kind: str, coordinate: str) -> None:
        opts = tf.options_of(kind, lists)
        if not opts:
            return
        key = json.dumps(sorted(opts.items()))
        if key not in ranges:
            col = len(ranges) + 1
            for i, (c, w) in enumerate(opts.items(), start=1):
                lists_ws.cell(row=i, column=col, value=f"{c} - {w}")
            ranges[key] = f"Lists!${_letter(col)}$1:${_letter(col)}${len(opts)}"
        dv = DataValidation(type="list", formula1=ranges[key], allow_blank=True, showErrorMessage=False)
        ws.add_data_validation(dv)
        dv.add(coordinate)

    def header(ws, title: str, cols: List[tf.Field], first: List[str]):
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([""] * len(first) + [f"Form {f}" for f, *_ in cols])
        ws.append(first + [label for _, _, label, _ in cols] + ["staff id", "downloaded"])
        ws.append([""] * len(first) + [allowed(kind, lists) for *_, kind in cols])
        for i, (f, *_) in enumerate(cols, start=len(first) + 1):
            ws.cell(row=2, column=i).fill, ws.cell(row=2, column=i).font = form_fill[f], white
        for c in ws[3]:
            c.font, c.fill, c.alignment = white, blue, wrap
        for c in ws[4]:
            c.alignment, c.font = wrap, Font(italic=True, size=8, color="64748B")
        ws.row_dimensions[3].height = 60
        ws.row_dimensions[4].height = 45
        for i in range(1, len(first) + len(cols) + 1):
            ws.column_dimensions[_letter(i)].width = 26 if i == 2 else 18
        hidden = len(first) + len(cols) + 1
        ws.column_dimensions[_letter(hidden)].hidden = True
        ws.column_dimensions[_letter(hidden + 1)].hidden = True
        ws.freeze_panes = f"{_letter(len(first) + 1)}{FIRST_ROW}"
        return hidden

    sheets = {}
    for staff_type, label in tf.STAFF_TYPES.items():
        ws = wb.create_sheet(_sheet(staff_type))
        sheets[str(staff_type)] = ws.title
        cols = tf.columns(staff_type)
        hidden = header(ws, f"{label} - {len([s for s in data['staff'] if s['type'] == staff_type])} on UDISE+", cols,
                        ["National code", "Name on UDISE+", "Forms complete?"])
        for s in [s for s in data["staff"] if s["type"] == staff_type]:
            raw = {f"{f}:{k}": _value(s, f, k) for f, k, _, _ in cols}
            ws.append([s["national_code"], s["name"], "Yes" if str(s.get("form_flag")) == "3" else "No"]
                      + [show(kind, raw[f"{f}:{k}"], lists) for f, k, _, kind in cols] + [str(s["id"]), json.dumps(raw)])
            r = ws.max_row
            for i, (f, k, _, kind) in enumerate(cols, start=VISIBLE_FIRST + 1):
                cell = ws.cell(row=r, column=i)
                cell.protection = Protection(locked=False)
                cell.fill = needed_fill if f not in s["errors"] and _asked(s, k) and _blank(kind, raw[f"{f}:{k}"]) else answer_fill
                if kind in ("text", "mobile", "aadhaar", "date", "email"):
                    cell.number_format = "@"
                validation(ws, kind, cell.coordinate)
        ws.protection.sheet = True
        ws.protection.formatColumns = False
    new = wb.create_sheet("New staff")
    new_cols = tf.columns(1, new=True)
    header(new, "New staff to add on UDISE+ (one row each)", new_cols, ["Staff type (1 teaching, 2 non-teaching, 4 special educator)"])
    for r in range(FIRST_ROW, FIRST_ROW + 30):
        for i, (f, k, _, kind) in enumerate(new_cols, start=2):
            cell = new.cell(row=r, column=i)
            if kind in ("text", "mobile", "aadhaar", "date", "email"):
                cell.number_format = "@"
            validation(new, kind, cell.coordinate)
    for k, v in {"kind": WORKBOOK_KIND, "school_id": data["school_id"], "read_at": data["read_at"], "sheets": sheets}.items():
        meta_ws.append([k, json.dumps(v)])
    lists_ws.sheet_state = meta_ws.sheet_state = "hidden"
    out = io.BytesIO()
    keep_text(wb)
    grid_sheets(wb)                        # clear cell borders (a fill hides the gridlines)
    wb.save(out)
    return out.getvalue(), f"UDISE_Teachers_{school.get('udiseCode') or data['school_id']}.xlsx"


# ---------------------------------------------------------------- checking a filled workbook

def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    from openpyxl import load_workbook
    data = load(school_id)
    if not data:
        return {"ok": False, "error": "Read the staff from UDISE+ first."}
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read (.xlsx)."}
    meta = {}
    if "_meta" in wb.sheetnames:
        for row in wb["_meta"].iter_rows(values_only=True):
            try:
                meta[str(row[0])] = json.loads(row[1])
            except (TypeError, ValueError, IndexError):
                pass
    if meta.get("kind") != WORKBOOK_KIND:
        return {"ok": False, "error": "This is not the Teacher workbook from this app. Download it again here."}
    if str(meta.get("school_id")) != str(data["school_id"]):
        return {"ok": False, "error": "This workbook is for another school."}
    lists = data["lists"]
    by_id = {str(s["id"]): s for s in data["staff"]}
    people, problems_total = [], 0
    for staff_type, name in (meta.get("sheets") or {}).items():
        if name not in wb.sheetnames:
            continue
        ws, cols = wb[name], tf.columns(int(staff_type))
        hidden = VISIBLE_FIRST + len(cols) + 1
        for r in range(FIRST_ROW, ws.max_row + 1):
            sid = ws.cell(row=r, column=hidden).value
            s = by_id.get(str(sid))
            if not s:
                continue
            try:
                downloaded = json.loads(ws.cell(row=r, column=hidden + 1).value or "{}")
            except ValueError:
                downloaded = {}
            changes, problems = [], []
            for i, (f, k, label, kind) in enumerate(cols, start=VISIBLE_FIRST + 1):
                before = downloaded.get(f"{f}:{k}")
                value, problem = parse(kind, ws.cell(row=r, column=i).value, lists, like=before)
                problem = problem or _name_ok(k, value)
                if problem:
                    problems.append(f"{label} ({_letter(i)}{r}): {problem}")
                    continue
                if value is None or _same(value, before) or _same(show(kind, value, lists), show(kind, before, lists)):
                    continue
                now = _value(s, f, k)
                changes.append({"form": f, "key": k, "label": label, "cell": f"{_letter(i)}{r}",
                                "old": show(kind, now, lists), "new": show(kind, value, lists), "value": value,
                                "downloaded": before, "warning": "" if _same(now, before) else
                                "Changed on UDISE+ after the download: left as UDISE+ has it."})
            if changes or problems:
                people.append({"staff_id": s["id"], "type": s["type"], "name": s["name"], "national_code": s["national_code"],
                               "sheet": name, "row": r, "changes": changes, "problems": problems, "new": False})
                problems_total += len(problems)
    if "New staff" in wb.sheetnames:
        ws, cols = wb["New staff"], tf.columns(1, new=True)
        for r in range(FIRST_ROW, ws.max_row + 1):
            cells = [ws.cell(row=r, column=i).value for i in range(1, len(cols) + 2)]
            if not any(c not in (None, "") for c in cells):
                continue
            problems, values = [], {}
            try:
                staff_type = int(str(cells[0]).strip()[0])
                assert staff_type in tf.STAFF_TYPES
            except (ValueError, AssertionError, IndexError):
                staff_type = None
                problems.append(f"Staff type (A{r}): 1, 2 or 4.")
            these = tf.columns(staff_type or 1, new=True)
            for i, (f, k, label, kind) in enumerate(cols, start=2):
                if (f, k) not in [(x[0], x[1]) for x in these]:
                    continue
                value, problem = parse(kind, ws.cell(row=r, column=i).value, lists)
                problem = problem or _name_ok(k, value)
                if problem:
                    problems.append(f"{label} ({_letter(i)}{r}): {problem}")
                elif value is None and f == "1" and k not in tf.OPTIONAL:
                    problems.append(f"{label} ({_letter(i)}{r}): needed for a new staff member.")
                elif value is not None:
                    values[f"{f}:{k}"] = value
            people.append({"staff_id": None, "type": staff_type, "name": values.get("1:empName") or "(no name)",
                           "national_code": "", "sheet": "New staff", "row": r, "new": True, "problems": problems,
                           "changes": [{"form": key.split(":")[0], "key": key.split(":")[1], "label": key, "cell": "",
                                        "old": None, "new": show(next(k for f, kk, _, k in cols if f"{f}:{kk}" == key), v, lists)
                                        if key != "1:referenceKey" else "xxxx-xxxx-" + str(v)[-4:], "value": v,
                                        "downloaded": None, "warning": ""} for key, v in values.items()]})
            problems_total += len(problems)
    plan = {"ok": True, "file_name": file_name, "checked_at": _now(), "people": people, "problems": problems_total,
            "changes": sum(len([c for c in p["changes"] if not c["warning"]]) for p in people if not p["new"]),
            "new_staff": sum(1 for p in people if p["new"]), "save_enabled": SAVE_ENABLED, "results": None}
    _write(school_id, "udise_teacher_plan.json", plan)
    return public_plan(plan)


def public_plan(plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not plan:
        return None
    out = copy.deepcopy(plan)
    for p in out["people"]:
        for c in p["changes"]:
            c.pop("value", None)
            c.pop("downloaded", None)
    out["save_enabled"] = SAVE_ENABLED
    return out


def last_plan(school_id: str) -> Optional[Dict[str, Any]]:
    return _read(school_id, "udise_teacher_plan.json")


# ---------------------------------------------------------------- saving

def _body(staff_type: int, form: str, fresh: Dict[str, Any], edits: Dict[str, Any], sid: Any, emp: Any) -> Dict[str, Any]:
    """The request the page sends for a form: its fields (the read values with the edits) and the ids it adds."""
    fields = [k for f, k, _, _ in tf.columns(staff_type) if f == form]
    values = {k: edits.get(k, fresh.get(k)) for k in fields}
    if form == "1":
        values.update(mobileYN=bool(fresh.get("mobileYN")), aadharYN=False, uidMasking=fresh.get("uidMasking"),
                      crrNo=fresh.get("crrNo"), specialEdu=fresh.get("specialEdu"), createdFlag=False, schoolId=sid,
                      empType=staff_type, empStaffId=emp)
        if staff_type != 1:
            values.setdefault("qualProf", fresh.get("qualProf"))
        return values
    if form == "2" and staff_type == 4:
        return {"empStaffId": emp, "postId": values.get("postId"), "classesTaught": values.get("classesTaught"),
                "natureOfAppt": values.get("natureOfAppt"), "dojService": values.get("dojService"), "dojPs": values.get("dojPs"),
                "dateCurrPostHeld": values.get("dateCurrPostHeld"), "schoolId": sid, "empType": staff_type}
    values.update(empStaffId=emp, schoolId=sid)
    if form == "2":
        values["empType"] = staff_type
    return values


def save(school_id: str, only: Optional[List[int]] = None) -> Dict[str, Any]:
    if not SAVE_ENABLED:
        return {"ok": False, "error": "Saving staff to UDISE+ is not switched on yet: the app first checks the Teacher "
                                      "service's answers against this school's real data. Nothing was sent."}
    plan = last_plan(school_id)
    if not plan:
        return {"ok": False, "error": "Upload and check a workbook first."}
    lock = _LOCKS.setdefault(school_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"ok": False, "error": "A save is already running."}
    results = []
    try:
        svc = _service(school_id)
        sid = svc.region_id
        for p in plan["people"]:
            if p["new"] or p["problems"] or (only and p["staff_id"] not in only):
                continue
            by_form: Dict[str, Dict[str, Any]] = {}
            for c in p["changes"]:
                if not c["warning"]:
                    by_form.setdefault(c["form"], {})[c["key"]] = c
            for form, changes in sorted(by_form.items()):
                read, write = tf.paths(p["type"], sid, p["staff_id"])[form]
                try:
                    fresh = svc.get(read) or {}
                    edits = {k: c["value"] for k, c in changes.items() if _same(fresh.get(k), c["downloaded"])}
                    skipped = [c["label"] for k, c in changes.items() if k not in edits]
                    if not edits:
                        results.append({"name": p["name"], "form": form, "status": "skipped", "message": "changed on UDISE+ meanwhile"})
                        continue
                    _snapshot(school_id, p["staff_id"], form, fresh)
                    svc.post(write, _body(p["type"], form, fresh, edits, sid, p["staff_id"]))
                    after = svc.get(read) or {}
                    wrong = [changes[k]["label"] for k, v in edits.items() if not _same(after.get(k), v)]
                    _add_history(school_id, [{"at": _now(), "staff": p["name"], "national_code": p["national_code"],
                                              "form": f"Form {form}", "field": changes[k]["label"], "before": changes[k]["old"],
                                              "after": changes[k]["new"], "result": "check on UDISE+" if changes[k]["label"] in wrong
                                              else "saved and confirmed"} for k in edits])
                    results.append({"name": p["name"], "form": form, "status": "saved" if not wrong else "check",
                                    "message": "; ".join(filter(None, [("left as on UDISE+: " + ", ".join(skipped)) if skipped else "",
                                                                       ("UDISE+ shows other values for: " + ", ".join(wrong)) if wrong else ""]))})
                except bearer.Refused as exc:
                    results.append({"name": p["name"], "form": form, "status": "refused", "message": str(exc)})
    except bearer.SessionEnded as exc:
        results.append({"name": "", "form": "", "status": "error", "message": str(exc)})
    finally:
        lock.release()
    plan["results"] = {"at": _now(), "items": results}
    _write(school_id, "udise_teacher_plan.json", plan)
    return {"ok": True, "results": results}


def _snapshot(school_id: str, staff_id: Any, form: str, data: Any) -> None:
    d = inside(DATA_DIR / "snapshots", f"school_{school_id}", "udise_teacher", str(staff_id))
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = d / f"{now:%Y%m%dT%H%M%S%fZ}_form{form}.json"
    path.write_text(json.dumps({"taken_at": now.isoformat(timespec="seconds"), "data": data}, ensure_ascii=False), encoding="utf-8")
    json.loads(path.read_text(encoding="utf-8"))
