"""
UDISE+ School Profile & Facilities for the current session, with an Excel workbook (DCF 1.31 to 2.28).

overview()   reads every form from UDISE+: session, when each was last saved, how many answers are given
excel()      the workbook: one sheet per form, a row per question, this year's answers already filled in
validate()   a filled workbook -> the changes, form by form, and any problems. Sends nothing.
save()       saves the checked changes, form by form in DCF order. Before each save the form is read again;
             a copy of it is kept (data/snapshots/school_<id>/udise_profile/); only the edited answers change.
             An answer someone changed on UDISE+ after the download is not overwritten (reported instead).
Certifying the data stays on the UDISE+ website (it locks the data; the head of school does it).
"""
import copy
import io
import json
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DATA_DIR
from backend.hpc.xl import grid_sheets, keep_text
from backend.services import secrets_box, udise_sessions
from backend.services.hpc_sessions import session_dir
from backend.services.safe_paths import inside
from backend.udise import bearer, client
from backend.udise import profile_forms as pf

WORKBOOK_KIND = "udise_profile_v1"
_LOCKS: Dict[str, threading.Lock] = {}


def _lock(school_id: str) -> threading.Lock:
    return _LOCKS.setdefault(school_id, threading.Lock())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _service(school_id: str) -> bearer.Service:
    return bearer.Service(school_id, "profile", udise_sessions.load_saved(school_id))


# ---------------------------------------------------------------- reading

def read_all(school_id: str, svc: Optional[bearer.Service] = None) -> Dict[str, Any]:
    """Everything the workbook needs, read from UDISE+ now: the school's basic profile, the option lists and
    every form."""
    svc = svc or _service(school_id)
    sid = svc.region_id
    school = svc.get(f"/school/{sid}") or {}
    lists = {}
    for name, path in pf.OPTION_LISTS.items():
        try:
            raw = svc.get(f"/school/{sid}/{path}") or {}
            lists[name] = {int(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        except (bearer.Refused, ValueError):
            lists[name] = {}
    forms = {}
    for form in pf.FORMS:
        try:
            forms[form["key"]] = {"data": svc.get(f"/school/{sid}/{form['path']}"), "error": None}
        except bearer.Refused as exc:
            forms[form["key"]] = {"data": None, "error": str(exc)}
    return {"school_id": sid, "school": school, "lists": lists, "forms": forms, "read_at": _now()}


def _year(data: Any) -> str:
    first = data[0] if isinstance(data, list) and data else data
    return str((first or {}).get("smlAcademicYear") or "") if isinstance(first, dict) else ""


def _form_meta(data: Any) -> Dict[str, Any]:
    first = data[0] if isinstance(data, list) and data else data
    if not isinstance(first, dict):
        return {"year": "", "modified": "", "certified": False, "status": None}
    rows = data if isinstance(data, list) else [data]
    times = [str(r.get("modifiedTime") or "") for r in rows if isinstance(r, dict)]
    return {"year": str(first.get("smlAcademicYear") or ""), "modified": max(times) if times else "",
            "certified": any(bool(r.get("certificationStatus")) for r in rows if isinstance(r, dict)),
            "status": first.get("formStatus")}


def _value(form: Dict[str, Any], data: Any, q: Dict[str, Any]) -> Any:
    if form.get("table"):
        row = next((r for r in data or [] if (r.get("id") or {}).get("itemId") == q["row"]), None)
        return None if row is None else row.get(q["col"])
    return (data or {}).get(q["id"]) if isinstance(data, dict) else None


def _blank(kind: Any, value: Any) -> bool:
    """Not answered: nothing, or a coded answer stored as 0/9 (UDISE+'s 'not given / not applicable')."""
    if value is None or value == "":
        return True
    if pf.options(kind) is not None or (isinstance(kind, str) and kind.startswith("opt:")):
        if isinstance(value, list):
            return not value
        return str(value).strip() in ("0", "9")
    if kind in ("classes", "year"):
        return str(value).strip() in ("0", "")
    return False


def rows_of(form: Dict[str, Any], levels: set) -> List[Dict[str, Any]]:
    """The questions of a form in the workbook, in order, each with its sheet row: the same list for the workbook,
    the check of an upload and the report (so 'sheet, row' in a report is where the question is in the file)."""
    out = []
    for q in pf.questions(form):
        if pf.applies(q, levels) and pf.for_school(q["id"], levels):
            out.append({**q, "row_no": FIRST_ROW + len(out)})
    return out


FIRST_ROW = 5


def overview(school_id: str) -> Dict[str, Any]:
    return status(school_id, read_all(school_id))


def status(school_id: str, found: Dict[str, Any]) -> Dict[str, Any]:
    """Where the school stands, exactly: per form how many asked questions are answered; every question still
    needed with its DCF item and its place in the workbook; totals that do not add up; and what was updated from
    the app (the history)."""
    school, lists = found["school"], found["lists"]
    levels = pf.school_levels(school)
    forms, needed, problems = [], [], []
    for form in pf.FORMS:
        entry = found["forms"][form["key"]]
        data = entry["data"]
        meta = _form_meta(data)
        asked = [q for q in rows_of(form, levels) if data is not None and pf.asked(form, q, data, levels)]
        missing = [q for q in asked if _blank(q["kind"], _value(form, data, q))]
        for q in missing:
            needed.append({"form": form["key"], "dcf": form["dcf"], "title": form["title"], "item": q["item"],
                           "question": q["question"], "sheet": _sheet_name(form), "row": q["row_no"],
                           "allowed": allowed(q["kind"], lists)})
        if isinstance(data, dict):
            for m in _checks(form["key"], data):
                problems.append({"form": form["key"], "dcf": form["dcf"], "title": form["title"], "message": m})
        forms.append({"key": form["key"], "dcf": form["dcf"], "title": form["title"], "sheet": _sheet_name(form),
                      "questions": len(asked), "answered": len(asked) - len(missing), "needed": len(missing),
                      "error": entry["error"], **meta})
    years = [f["year"] for f in forms if f["year"]]
    history = load_history(school_id)
    return {"school": {"name": school.get("schoolName"), "udise_code": school.get("udiseCode"),
                       "category": school.get("schCategoryId"), "session_from": school.get("acadYearStartDate"),
                       "session_to": school.get("acadYearEndDate")},
            "year": max(years) if years else str(school.get("smlAcademicYear") or ""), "forms": forms,
            "needed": needed, "problems": problems, "updated": history, "read_at": found["read_at"]}


# ---------------------------------------------------------------- what the app saved (the history for the report)

def _history_file(school_id: str):
    return session_dir("school", school_id) / "udise_profile_history.json"


def load_history(school_id: str) -> List[Dict[str, Any]]:
    path = _history_file(school_id)
    if not path.exists():
        return []
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:
        return []


def _add_history(school_id: str, entries: List[Dict[str, Any]]) -> None:
    if not entries:
        return
    found = load_history(school_id) + entries
    path = _history_file(school_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(found[-5000:], ensure_ascii=False)), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- answers in words and back

def show(kind: Any, value: Any, lists: Dict[str, Dict[int, str]]) -> Any:
    """An answer as the workbook shows it: '1 - Yes', a number, or words. Not answered: empty."""
    if _blank(kind, value):
        return None
    opts = pf.options(kind, lists)
    if isinstance(kind, str) and kind.startswith("multi:"):
        codes = value if isinstance(value, list) else [v for v in str(value).split(",") if v.strip()]
        return ", ".join(f"{int(c)} - {opts.get(int(c), '?')}" for c in codes)
    if opts is not None:
        try:
            code = int(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{code} - {opts[code]}" if code in opts else str(code)
    if kind in ("num",):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if kind in ("dec", "money"):
        try:
            d = Decimal(str(value))
            return int(d) if d == d.to_integral_value() else float(d)
        except InvalidOperation:
            return value
    return str(value)


def allowed(kind: Any, lists: Dict[str, Dict[int, str]]) -> str:
    opts = pf.options(kind, lists)
    if isinstance(kind, str) and kind.startswith("multi:"):
        return "One or more, with commas: " + ", ".join(f"{c} - {w}" for c, w in opts.items())
    if opts is not None:
        return ", ".join(f"{c} - {w}" for c, w in opts.items()) or "(list from UDISE+)"
    return {"num": "Whole number (0 or more)", "dec": "Number, up to 2 decimals", "money": "Amount in rupees",
            "year": "Year, e.g. 2024", "classes": "Class numbers with commas, e.g. 1,2", "text": "Words"}.get(kind, "")


def parse(kind: Any, cell: Any, lists: Dict[str, Dict[int, str]]) -> Tuple[Any, Optional[str]]:
    """A workbook answer -> (the value UDISE+ stores, problem). An empty cell is (None, None): left as it is."""
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None, None
    text = str(cell).strip()
    opts = pf.options(kind, lists)
    if isinstance(kind, str) and kind.startswith("multi:"):
        codes = []
        for part in re.split(r"[,;/]+", text):
            m = re.match(r"\s*(\d+)", part)
            if not m or int(m.group(1)) not in opts:
                return None, f"'{part.strip()}' is not one of: " + ", ".join(f"{c} - {w}" for c, w in opts.items())
            codes.append(int(m.group(1)))
        return sorted(set(codes)), None
    if opts is not None:
        m = re.match(r"^\s*(\d+)\b", text)
        code = int(m.group(1)) if m else next((c for c, w in opts.items() if w.lower() == text.lower()), None)
        if code is None or (opts and code not in opts):
            return None, f"'{text}' is not one of the allowed answers."
        return code, None
    if kind == "num":
        try:
            d = Decimal(text)
        except InvalidOperation:
            return None, f"'{text}' is not a number."
        if d < 0 or d != d.to_integral_value():
            return None, f"'{text}' should be a whole number, 0 or more."
        return int(d), None
    if kind in ("dec", "money"):
        try:
            d = Decimal(text.replace(",", "") if kind == "money" else text)
        except InvalidOperation:
            return None, f"'{text}' is not a number."
        if d < 0:
            return None, "The number cannot be below 0."
        if kind == "dec" and d != round(d, 2):
            return None, f"'{text}' has more than 2 decimals."
        return float(d), None
    if kind == "year":
        m = re.fullmatch(r"(\d{4})(\.0)?", text)
        if not m or not 1900 <= int(m.group(1)) <= 2100:
            return None, f"'{text}' is not a year like 2024."
        return m.group(1), None
    if kind == "classes":
        parts = [p.strip() for p in re.split(r"[,;\s]+", text) if p.strip()]
        try:
            nums = sorted({int(float(p)) for p in parts})
        except ValueError:
            return None, f"'{text}' should be class numbers with commas, e.g. 1,2."
        if any(n < -3 or n > 12 for n in nums):
            return None, "Classes run from -3 (pre-primary) to 12."
        return ",".join(str(n) for n in nums), None
    if len(text) > 200:
        return None, "Too long (more than 200 characters)."
    return text, None


def _same(kind: Any, a: Any, b: Any) -> bool:
    if _blank(kind, a) and _blank(kind, b):
        return True
    if isinstance(a, list) or isinstance(b, list):
        return sorted(a or []) == sorted(b or [])
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a or "").strip() == str(b or "").strip()


# ---------------------------------------------------------------- the workbook

def _sheet_name(form: Dict[str, Any]) -> str:
    name = f"{form['dcf'].replace(' to ', '-')} {form['title']}"
    return re.sub(r"[\\/*?:\[\]]", "-", name)[:31]


def excel(school_id: str) -> Tuple[bytes, str]:
    """The workbook and its file name."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.worksheet.datavalidation import DataValidation

    found = read_all(school_id)
    school, lists = found["school"], found["lists"]
    levels = pf.school_levels(school)
    years = [_year(f["data"]) for f in found["forms"].values() if f["data"]]
    year = max(years) if years else ""
    code = str(school.get("udiseCode") or "")
    blue, white = PatternFill("solid", fgColor="0B5FA5"), Font(bold=True, color="FFFFFF")
    answer_fill = PatternFill("solid", fgColor="FFF7D6")
    needed_fill = PatternFill("solid", fgColor="FDE2E2")
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    lines = [
        (f"UDISE+ School Profile & Facilities - session {year}", Font(bold=True, size=14)),
        (f"{school.get('schoolName', '')} (UDISE code {code})", Font(bold=True)),
        (f"Downloaded {found['read_at'][:16].replace('T', ' ')} UTC. Answers are what UDISE+ holds for {year} now.", None),
        ("", None),
        ("How to fill it", Font(bold=True)),
        ("1. Each sheet is one form of the UDISE+ Data Capture Format (DCF), each row one question.", None),
        ("2. Change only the yellow 'Answer' column. Pick from the list or type the number, e.g. 1 for '1 - Yes'.", None),
        ("3. An empty answer is left as it is on UDISE+. Rows marked 'Needed' (pink) are asked of the school and still empty.", None),
        ("4. Upload the file in the app. It shows every change before anything is sent to UDISE+.", None),
        ("5. Then certify the data on the UDISE+ website (School Profile > Certification): the app does not certify.", None),
        ("", None),
        ("Saving a form that was already certified removes its certification: certify again after saving.", Font(bold=True, color="B45309")),
        ("Questions that do not apply to the school (classes it does not have) are left out.", None),
        ("Not in this file, change them on the website: 1.1-1.30 basic details, 1.63 NSQF, the state's own questions, "
         "the sports list of 2.13 and 2.1(a).", None),
        ("", None),
        ("Forms", Font(bold=True)),
    ]
    for text, font in lines:
        readme.append([text])
        if font:
            readme.cell(row=readme.max_row, column=1).font = font
    readme.append(["DCF items", "Form", "Questions", "Last saved on UDISE+", "Certified"])
    for c in readme[readme.max_row]:
        c.font, c.fill = white, blue
    readme.column_dimensions["A"].width = 22
    readme.column_dimensions["B"].width = 70
    readme.column_dimensions["C"].width = 12
    readme.column_dimensions["D"].width = 22

    lists_ws = wb.create_sheet("Lists")
    list_ranges: Dict[str, str] = {}
    meta_ws = wb.create_sheet("_meta")
    meta = {"kind": WORKBOOK_KIND, "udise_code": code, "school_id": found["school_id"], "year": year,
            "downloaded_at": found["read_at"]}
    sheets = {}

    for form in pf.FORMS:
        entry = found["forms"][form["key"]]
        info = _form_meta(entry["data"])
        qs = rows_of(form, levels)
        readme.append([form["dcf"], form["title"], len(qs), info["modified"] or "-",
                       "Yes" if info["certified"] else "No"])
        if entry["data"] is None:
            readme.cell(row=readme.max_row, column=2).value = f"{form['title']} - could not be read: {entry['error'] or 'no data'}"
            continue
        ws = wb.create_sheet(_sheet_name(form))
        sheets[form["key"]] = ws.title
        ws.append([f"{form['dcf']}  {form['title']}  -  session {info['year'] or year}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([form.get("note") or ("Already certified: saving this form removes the certification."
                                        if info["certified"] else "")])
        ws["A2"].font = Font(italic=True, color="B45309")
        ws.append([])
        ws.append(["Item", "Question", "Answer", "Allowed answers", "field", "downloaded", "Status"])
        for c in ws[4]:
            c.font, c.fill, c.alignment = white, blue, wrap
        for q in qs:
            raw = _value(form, entry["data"], q)
            ws.append([q["item"], q["question"], show(q["kind"], raw, lists), allowed(q["kind"], lists),
                       q["id"], json.dumps(raw)])
            r = ws.max_row
            ws.cell(row=r, column=2).alignment = wrap
            ws.cell(row=r, column=4).alignment = wrap
            answer = ws.cell(row=r, column=3)
            answer.fill, answer.protection = answer_fill, Protection(locked=False)
            if pf.asked(form, q, entry["data"], levels) and _blank(q["kind"], raw):
                ws.cell(row=r, column=7, value="Needed").font = Font(bold=True, color="B91C1C")
                answer.fill = needed_fill
            if q["kind"] in ("text", "classes", "year"):
                answer.number_format = "@"
            opts = pf.options(q["kind"], lists)
            if opts and not (isinstance(q["kind"], str) and q["kind"].startswith("multi:")):
                key = json.dumps(sorted(opts.items()))
                if key not in list_ranges:
                    col = len(list_ranges) + 1
                    for i, (c, w) in enumerate(opts.items(), start=1):
                        lists_ws.cell(row=i, column=col, value=f"{c} - {w}")
                    from openpyxl.utils import get_column_letter
                    letter = get_column_letter(col)
                    list_ranges[key] = f"Lists!${letter}$1:${letter}${len(opts)}"
                dv = DataValidation(type="list", formula1=list_ranges[key], allow_blank=True, showErrorMessage=False)
                ws.add_data_validation(dv)
                dv.add(answer.coordinate)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 70
        ws.column_dimensions["C"].width = 26
        ws.column_dimensions["D"].width = 40
        ws.column_dimensions["E"].hidden = True
        ws.column_dimensions["F"].hidden = True
        ws.column_dimensions["G"].width = 10
        ws.freeze_panes = "C5"
        ws.protection.sheet = True                    # only the answers can be changed (no password)
        ws.protection.formatColumns = False
        ws.protection.formatRows = False

    meta["sheets"] = sheets
    for k, v in meta.items():
        meta_ws.append([k, json.dumps(v)])
    lists_ws.sheet_state = "hidden"
    meta_ws.sheet_state = "hidden"
    out = io.BytesIO()
    keep_text(wb)
    grid_sheets(wb)                        # clear cell borders (a fill hides the gridlines)
    wb.save(out)
    safe_year = re.sub(r"[^0-9-]", "", year) or "current"
    return out.getvalue(), f"UDISE_School_Profile_{code}_{safe_year}.xlsx"


# ---------------------------------------------------------------- checking a filled workbook

def _plan_file(school_id: str):
    return session_dir("school", school_id) / "udise_profile_plan.json"


def _write_plan(school_id: str, plan: Dict[str, Any]) -> None:
    path = _plan_file(school_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(plan, ensure_ascii=False)), encoding="utf-8")
    tmp.replace(path)


def last_plan(school_id: str) -> Optional[Dict[str, Any]]:
    path = _plan_file(school_id)
    if not path.exists():
        return None
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def public_plan(plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The plan without the raw values (the page shows words)."""
    if not plan:
        return None
    out = copy.deepcopy(plan)
    for f in out.get("forms", []):
        for c in f.get("changes", []):
            c.pop("value", None)
            c.pop("downloaded", None)
    return out


def _final(data: Any, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The answers of an object form after the changes (for the consistency checks)."""
    values = dict(data or {}) if isinstance(data, dict) else {}
    for c in changes:
        values[c["id"]] = c["value"]
    return values


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


CLASSROOMS = ("clsrmsPrePri", "clsrmsPri", "clsrmsUpr", "clsrmsSec", "clsrmsHsec")
BY_CONDITION = ("clsrmsGd", "clsrmsMin", "clsrmsMaj", "clsrmsDptdPucca", "clsrmsGdPpu", "clsrmsMinPpu", "clsrmsMajPpu",
                "clsrmsDptdPpu", "clsrmsGdKuc", "clsrmsMinKun", "clsrmsMajKuc", "clsrmsDptdKuc", "clsrmsGdTnt",
                "clsrmsMinTnt", "clsrmsMajTnt", "clsrmsDptdTnt")
NOT_IN_USE = ("clsrmsNuGdPucca", "clsrmsNuMin", "clsrmsNuMaj", "clsrmsNuDptdPucca", "clsrmsNuGdPpu", "clsrmsNuMinPpu",
              "clsrmsNuMajPpu", "clsrmsNuDptdPpu", "clsrmsNuGdKuc", "clsrmsNuMinKun", "clsrmsNuMajKuc", "clsrmsNuDptdKuc",
              "clsrmsNuGdTnt", "clsrmsNuMinTnt", "clsrmsNuMajTnt", "clsrmsNuDptdTnt")
DILAPIDATED = ("clsrmsDptdPucca", "clsrmsDptdPpu", "clsrmsDptdKuc", "clsrmsDptdTnt", "clsrmsNuDptdPucca",
               "clsrmsNuDptdPpu", "clsrmsNuDptdKuc", "clsrmsNuDptdTnt")


def _derive(form_key: str, values: Dict[str, Any]) -> None:
    """Fields the page itself fills in from others, filled the same way."""
    if form_key == "buildings":
        values["clsrmsInst"] = int(sum(_n(values.get(k)) for k in CLASSROOMS))
        values["clsrmsDptd"] = int(sum(_n(values.get(k)) for k in DILAPIDATED))
    if form_key == "safety" and str(values.get("cctvCamYn")) != "1":
        values["totalFunctionalCctvCameras"] = 0


def _checks(form_key: str, v: Dict[str, Any]) -> List[str]:
    """The page's own checks before it saves (UDISE+ refuses the same)."""
    out = []
    if form_key == "buildings":
        total = _n(v.get("bldBlkTot"))
        storeys = sum(_n(v.get(k)) for k in ("noSingleStorey", "noDoubleStorey", "noTripleStorey", "noMultiStorey"))
        if storeys != total:
            out.append(f"2.2: the storey-wise blocks add up to {storeys:g}, but the total of active building blocks is {total:g}.")
        rooms = sum(_n(v.get(k)) for k in CLASSROOMS)
        if str(v.get("bldStatus")) != "5":
            if total and not rooms:
                out.append("2.3(a): there should be at least 1 classroom when the school has building blocks.")
            if not total and rooms:
                out.append("2.3(a): classrooms for instruction should be 0 when the total of building blocks is 0.")
        cond = sum(_n(v.get(k)) for k in BY_CONDITION)
        if cond != rooms:
            out.append(f"2.3(b): classrooms by condition add up to {cond:g}, but the classrooms used for instruction "
                       f"(2.3(a), Pre-Primary to Higher Secondary) are {rooms:g}.")
        nu = sum(_n(v.get(k)) for k in NOT_IN_USE)
        if nu != _n(v.get("clsrmsNotInst")):
            out.append(f"2.3(c): classrooms not in use by condition add up to {nu:g}, but 'currently not in use' is "
                       f"{_n(v.get('clsrmsNotInst')):g}.")
    pairs = {"toilets": [("toiletb", "toiletbFun"), ("toiletg", "toiletgFun"), ("toiletbCwsn", "toiletbCwsnFun"),
                         ("toiletgCwsn", "toiletgCwsnFun"), ("urinalsb", "urinalsbFun"), ("urinalsg", "urinalsgFun")],
             "computers": [(q["id"], q2["id"]) for q, q2 in zip(pf.questions(pf.BY_KEY["computers"])[0:28:2],
                                                                 pf.questions(pf.BY_KEY["computers"])[1:28:2])]}
    for total, part in pairs.get(form_key, []):
        if _n(v.get(part)) > _n(v.get(total)):
            out.append(f"'{part}' ({_n(v.get(part)):g}) is more than its total '{total}' ({_n(v.get(total)):g}).")
    return out


def validate(school_id: str, content: bytes, file_name: str) -> Dict[str, Any]:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return {"ok": False, "error": "This is not an Excel file the app can read (.xlsx)."}
    if "_meta" not in wb.sheetnames:
        return {"ok": False, "error": "This is not the School Profile workbook from this app. Download it again here."}
    meta = {}
    for row in wb["_meta"].iter_rows(values_only=True):
        if row and row[0]:
            try:
                meta[str(row[0])] = json.loads(row[1]) if row[1] is not None else None
            except (TypeError, ValueError):
                meta[str(row[0])] = row[1]
    if meta.get("kind") != WORKBOOK_KIND:
        return {"ok": False, "error": "This is not the School Profile workbook from this app. Download it again here."}

    with _lock(school_id):
        found = read_all(school_id)
    school, lists = found["school"], found["lists"]
    code = str(school.get("udiseCode") or "")
    if str(meta.get("udise_code")) != code:
        return {"ok": False, "error": f"This workbook is for UDISE code {meta.get('udise_code')}, but the connected "
                                      f"school is {code}."}
    years = [_year(f["data"]) for f in found["forms"].values() if f["data"]]
    year = max(years) if years else ""
    if meta.get("year") and year and meta["year"] != year:
        return {"ok": False, "error": f"This workbook is for session {meta['year']}, but UDISE+ is now on {year}. "
                                      "Download a new workbook for this session."}
    levels = pf.school_levels(school)
    forms_out, total = [], 0
    for form in pf.FORMS:
        name = (meta.get("sheets") or {}).get(form["key"])
        if not name or name not in wb.sheetnames:
            continue
        ws = wb[name]
        known = {q["id"]: q for q in rows_of(form, levels)}
        current = found["forms"][form["key"]]["data"]
        info = _form_meta(current)
        changes, problems, seen = [], [], set()
        for r in range(5, ws.max_row + 1):
            qid = ws.cell(row=r, column=5).value
            if not qid or qid not in known or qid in seen:
                continue
            seen.add(qid)
            q = known[qid]
            try:
                downloaded = json.loads(ws.cell(row=r, column=6).value or "null")
            except (TypeError, ValueError):
                downloaded = None
            value, problem = parse(q["kind"], ws.cell(row=r, column=3).value, lists)
            if problem:
                problems.append({"item": q["item"], "question": q["question"], "message": problem})
                continue
            if value is None or _same(q["kind"], value, downloaded):
                continue
            now = _value(form, current, q)
            moved = not _same(q["kind"], now, downloaded)
            changes.append({"id": qid, "item": q["item"], "question": q["question"],
                            "old": show(q["kind"], now, lists), "new": show(q["kind"], value, lists),
                            "value": value, "downloaded": downloaded,
                            "warning": "Changed on UDISE+ after the download: it will be left as UDISE+ has it."
                            if moved else ""})
        if not form.get("table") and changes:
            final = _final(current, [c for c in changes if not c["warning"]])
            problems += [{"item": form["dcf"], "question": "", "message": m} for m in _checks(form["key"], final)]
        if changes or problems:
            forms_out.append({"key": form["key"], "dcf": form["dcf"], "title": form["title"],
                              "certified": info["certified"], "changes": changes, "problems": problems})
            total += sum(1 for c in changes if not c["warning"])
    plan = {"ok": True, "file_name": file_name, "checked_at": _now(), "year": year, "udise_code": code,
            "school_name": school.get("schoolName"), "forms": forms_out, "total_changes": total,
            "blocked_forms": [f["dcf"] for f in forms_out if f["problems"]], "results": None}
    _write_plan(school_id, plan)
    return public_plan(plan)


# ---------------------------------------------------------------- saving

def _snapshot(school_id: str, form_key: str, data: Any) -> None:
    """A copy of the form as UDISE+ held it, just before the save. No copy, no save."""
    d = inside(DATA_DIR / "snapshots", f"school_{school_id}", "udise_profile")
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = d / f"{now:%Y%m%dT%H%M%S%fZ}_{form_key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"taken_at": now.isoformat(timespec="seconds"), "form": form_key, "data": data},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    json.loads(path.read_text(encoding="utf-8"))


def _body(form: Dict[str, Any], fresh: Any, changes: List[Dict[str, Any]], sid: int) -> Tuple[Any, List[str]]:
    """What the page would send: the form as just read, without the fields it never sends, with the changes.
    Also the answers left alone because they changed on UDISE+ since the download."""
    skipped = []
    if form.get("table"):
        rows = [{k: v for k, v in r.items() if k not in pf.ROW_NOT_SENT} for r in fresh or []]
        for c in changes:
            item_id, col = c["id"].split(":")
            row = next((r for r in rows if str((r.get("id") or {}).get("itemId")) == item_id), None)
            if row is None:
                skipped.append(c["item"])
                continue
            if not _same(None, row.get(col), c["downloaded"]):
                skipped.append(c["item"])
                continue
            row[col] = c["value"]
        return rows, skipped
    body = {k: v for k, v in (fresh or {}).items() if k not in pf.NOT_SENT}
    body["schoolId"] = int(sid)
    for c in changes:
        if not _same(None, body.get(c["id"]), c["downloaded"]):
            skipped.append(c["item"])
            continue
        body[c["id"]] = c["value"]
    _derive(form["key"], body)
    return body, skipped


def save(school_id: str, only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Saves the last checked workbook, form by form in DCF order. Returns what happened to each form."""
    plan = last_plan(school_id)
    if not plan or not plan.get("forms"):
        return {"ok": False, "error": "Upload and check a workbook first."}
    if not _lock(school_id).acquire(blocking=False):
        return {"ok": False, "error": "A save is already running for this school."}
    results = []
    try:
        svc = _service(school_id)
        sid = svc.region_id
        for f in plan["forms"]:
            if only and f["key"] not in only:
                continue
            todo = [c for c in f["changes"] if not c.get("warning")]
            if f["problems"]:
                results.append({"key": f["key"], "dcf": f["dcf"], "status": "skipped",
                                "message": "Not saved: fix the problems in the workbook first."})
                continue
            if not todo:
                continue
            form = pf.BY_KEY[f["key"]]
            try:
                fresh = svc.get(f"/school/{sid}/{form['path']}")
                body, skipped = _body(form, fresh, todo, sid)
                if not form.get("table"):
                    problems = _checks(form["key"], body)
                    if problems:
                        results.append({"key": f["key"], "dcf": f["dcf"], "status": "skipped", "message": " ".join(problems)})
                        continue
                if len(skipped) == len(todo):
                    results.append({"key": f["key"], "dcf": f["dcf"], "status": "skipped",
                                    "message": "Every answer had changed on UDISE+ since the download: nothing sent."})
                    continue
                _snapshot(school_id, f["key"], fresh)
                svc.post(f"/school/{sid}/{form['path']}", body)
                after = svc.get(f"/school/{sid}/{form['path']}")
                wrong = []
                for c in todo:
                    if c["item"] in skipped:
                        continue
                    q = {"id": c["id"]}
                    if form.get("table"):
                        q.update(row=int(c["id"].split(":")[0]), col=c["id"].split(":")[1])
                    if not _same(None, _value(form, after, q), c["value"]):
                        wrong.append(c["item"])
                at = _now()
                _add_history(school_id, [
                    {"at": at, "year": plan.get("year"), "form": f["key"], "dcf": f["dcf"], "title": f["title"],
                     "sheet": _sheet_name(form), "item": c["item"], "question": c["question"], "before": c["old"],
                     "after": c["new"], "result": "check on UDISE+" if c["item"] in wrong else "saved and confirmed",
                     "file": plan.get("file_name")}
                    for c in todo if c["item"] not in skipped])
                results.append({"key": f["key"], "dcf": f["dcf"], "status": "saved" if not wrong else "check",
                                "saved": len(todo) - len(skipped) - len(wrong), "skipped": skipped,
                                "message": ("" if not wrong else
                                            "UDISE+ accepted the save but shows other answers for: " + ", ".join(wrong))})
            except bearer.SessionEnded:
                raise
            except bearer.Refused as exc:
                results.append({"key": f["key"], "dcf": f["dcf"], "status": "refused", "message": str(exc)})
            except client.UdiseError as exc:
                results.append({"key": f["key"], "dcf": f["dcf"], "status": "error", "message": str(exc)})
                break                                             # UDISE+ is not answering: stop here
    except bearer.SessionEnded as exc:
        results.append({"key": "", "dcf": "", "status": "error", "message": str(exc)})
    finally:
        _lock(school_id).release()
    plan["results"] = {"at": _now(), "forms": results}
    _write_plan(school_id, plan)
    from backend.services import audit
    audit.record(f"school_admin:{school_id}", "udise_profile_save", "udise", school_id, None,
                 {"forms": [{"dcf": r["dcf"], "status": r["status"]} for r in results]})
    return {"ok": True, "results": results}
