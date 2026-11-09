"""
School Register, phase 6: reports from what is saved - nothing is read from PARAKH or UDISE+ here.

school_report        Excel for the school: Summary per stage; every student (PARAKH identity, teacher, where the
                     card stands, attendance, father / name on the card, marks); By teacher; Needs attention
                     (no teacher, failed or to correct, attendance or marks missing).
reconciliation       the UDISE+ / APAAR / PARAKH comparison (udise_parakh.compare, on the register) as counts for the
                     dashboard, and reconciliation_report as Excel: Summary, APAAR, Differences, UDISE+ only,
                     PARAKH only.
teacher_report       Excel for one teacher: their students only.
"""
import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.services import register_data, register_status, school_register, udise_parakh

STAGES = ["Foundational", "Preparatory", "Middle"]


def _book():
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def _sheet(wb, title: str, heads: List[str], rows: List[List[Any]], widths: Optional[Dict[int, int]] = None):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    ws = wb.create_sheet(title[:31])
    ws.append(heads)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0B5FA5")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(["" if v is None else v for v in r])
    for i, h in enumerate(heads, start=1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, max(12, min(40, len(h) + 4)))
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{len(rows) + 1}"
    return ws


def _save(wb) -> bytes:
    from backend.hpc.xl import grid_sheets, keep_text
    keep_text(wb)                                     # names stay text, never formulas
    grid_sheets(wb)                        # clear cell borders (a fill hides the gridlines)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _students(school_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Optional[str]]:
    reg = school_register.students(school_id)["students"]
    try:
        session = register_data.session_of(school_id)
        entered = register_data.entered(school_id, session)
    except register_data.Problem:
        session, entered = None, {}
    return reg, entered, session


def _row(s: Dict[str, Any], e: Dict[str, Any]) -> List[Any]:
    card = s.get("card") or {}
    return [s["stage"], s["grade"], s["section"], s["student_name"], s["student_id"], s["apaar_id"], s["admission_number"],
            s["dob"], s["gender"], ", ".join(s["teachers"]) or "No teacher", card.get("status"), card.get("detail"),
            e.get("present") if e.get("months") else None, e.get("working") if e.get("months") else None,
            e.get("percent"), e.get("father"), e.get("card_name"),
            f"{e.get('marks', 0)} of {e.get('marks_of', 0)}" if e and e.get("marks_of") else None]


STUDENT_HEADS = ["Stage", "Class", "Section", "Name (as on PARAKH)", "PARAKH ID", "APAAR ID", "Admission no.", "Date of birth",
                 "Gender", "Teacher", "Card on PARAKH", "Card detail", "Days present", "Working days", "Attendance %",
                 "Father's name", "Name on the card", "Marks entered"]


def school_report(school_id: str) -> Tuple[bytes, str]:
    reg, entered, session = _students(school_id)
    wb = _book()
    summary = []
    for st in STAGES:
        rows = [s for s in reg if s["stage"] == st and not s["missing_on_parakh"]]
        if not rows:
            continue
        status = {k: sum(1 for s in rows if (s.get("card") or {}).get("status") == k) for k in register_status.ORDER}
        summary.append([st, len(rows), sum(1 for s in rows if s["teachers"]), sum(1 for s in rows if not s["teachers"]),
                        *[status[k] for k in register_status.ORDER],
                        sum(1 for s in rows if (entered.get(s["id"]) or {}).get("months")),
                        sum(1 for s in rows if (entered.get(s["id"]) or {}).get("marks"))])
    total = ["All stages"] + [sum(r[i] for r in summary) for i in range(1, len(summary[0]))] if summary else []
    _sheet(wb, "Summary", ["Stage", "Students", "With a teacher", "No teacher", *register_status.ORDER,
                           "Attendance entered", "Marks entered"], summary + ([total] if total else []))
    live = [s for s in reg if not s["missing_on_parakh"]]
    _sheet(wb, "Students", STUDENT_HEADS, [_row(s, entered.get(s["id"]) or {}) for s in live], {4: 32, 10: 24, 12: 40})
    by_teacher: Dict[str, Dict[str, Any]] = {}
    for s in live:
        for t in s["teachers"] or []:
            b = by_teacher.setdefault(t, {"classes": set(), "n": 0, **{k: 0 for k in register_status.ORDER}})
            b["classes"].add(f"{s['grade']} {s['section']}")
            b["n"] += 1
            b[(s.get("card") or {}).get("status") or "Fetched"] += 1
    _sheet(wb, "By teacher", ["Teacher", "Classes", "Students", *register_status.ORDER],
           [[t, ", ".join(sorted(b["classes"])), b["n"], *[b[k] for k in register_status.ORDER]]
            for t, b in sorted(by_teacher.items())], {1: 28, 2: 30})
    attention = []
    for s in live:
        e = entered.get(s["id"]) or {}
        status = (s.get("card") or {}).get("status")
        why = [w for w, bad in (("no teacher", not s["teachers"]),
                                (f"card: {status}", status in ("Submission failed", "Requires correction")),
                                ("attendance not entered", not e.get("months")),
                                ("marks not entered", e.get("marks_of") and e.get("marks", 0) < e.get("marks_of", 0)))
               if bad]
        if why:
            attention.append(_row(s, e) + ["; ".join(why)])
    _sheet(wb, "Needs attention", STUDENT_HEADS + ["Why"], attention, {4: 32, 19: 40})
    return _save(wb), f"School_Register_report_{session or ''}.xlsx"


def reconciliation(school_id: str) -> Dict[str, Any]:
    """The comparison's counts for the dashboard ({"ok": False, "error"} when UDISE+ was never fetched)."""
    r = udise_parakh.compare(school_id, [])
    if not r.get("ok"):
        return r
    from collections import Counter
    differs = Counter(f for m in r["matched"] for f in m["differs"])
    return {"ok": True, "source": r.get("source"), "counts": r["counts"], "apaar": r.get("apaar", {}),
            "differs": dict(differs.most_common())}


def _apaar_state(m: Dict[str, Any]) -> str:
    u, p = m["udise"]["apaar"], m["parakh"]["apaar"]
    if u and p:
        return "Same" if u == p else "Different"
    return "Only on UDISE+" if u else "Only on PARAKH" if p else "Missing on both"


def reconciliation_report(school_id: str) -> Tuple[bytes, str]:
    r = udise_parakh.compare(school_id, [])
    if not r.get("ok"):
        raise register_data.Problem(r.get("error") or "The comparison could not be made.")
    wb = _book()
    c, a = r["counts"], r.get("apaar", {})
    _sheet(wb, "Summary", ["", "Students"], [
        ["Compared from", r.get("source")], ["On UDISE+ (SDMS)", c["udise"]], ["On PARAKH", c["parakh"]],
        ["Matched", c["matched"]], ["Matched, with differences", c["differ"]], ["Only on UDISE+", c["only_udise"]],
        ["Only on PARAKH", c["only_parakh"]], ["APAAR missing on both (matched)", a.get("missing_both")],
        ["APAAR only on UDISE+", a.get("only_udise")], ["APAAR only on PARAKH", a.get("only_parakh")],
        ["APAAR different", a.get("differ")], ["Not matched and no APAAR", a.get("unmatched_without")],
        ["Made", datetime.now().strftime("%d %b %Y %H:%M")]], {1: 36, 2: 18})
    _sheet(wb, "APAAR", ["Name (UDISE+)", "Name (PARAKH)", "Class (PARAKH)", "APAAR on UDISE+", "APAAR on PARAKH", "APAAR",
                         "Matched by", "Card on PARAKH"],
           [[m["udise"]["name"], m["parakh"]["name"], m["parakh"]["class"], m["udise"]["apaar"], m["parakh"]["apaar"],
             _apaar_state(m), m["by"], m["parakh"].get("status")] for m in r["matched"]], {1: 30, 2: 30})
    diff_rows = []
    for m in r["matched"]:
        if not m["differs"]:
            continue
        u, p = m["udise"], m["parakh"]
        diff_rows.append([u["name"], p["name"], ", ".join(m["differs"]), u["class"], p["class"], u["dob"], p["dob"],
                          u["adm_no"], p["adm_no"], u["gender"], p["gender"], u.get("father"), p.get("father"), m["by"]])
    _sheet(wb, "Differences", ["Name (UDISE+)", "Name (PARAKH)", "What differs", "Class UDISE+", "Class PARAKH", "DOB UDISE+",
                               "DOB PARAKH", "Adm. no. UDISE+", "Adm. no. PARAKH", "Gender UDISE+", "Gender PARAKH",
                               "Father UDISE+", "Father (school)", "Matched by"], diff_rows, {1: 28, 2: 28, 3: 30})
    _sheet(wb, "Only on UDISE+", ["Name", "Class", "Date of birth", "Gender", "Admission no.", "APAAR", "PEN", "SDMS form"],
           [[x["name"], x["class"], x["dob"], x["gender"], x["adm_no"], x["apaar"], x.get("pen"), x["status"]]
            for x in r["only_udise"]], {1: 30})
    _sheet(wb, "Only on PARAKH", ["Name", "Class", "Date of birth", "Gender", "Admission no.", "APAAR", "PARAKH ID", "Card"],
           [[x["name"], x["class"], x["dob"], x["gender"], x["adm_no"], x["apaar"], x.get("parakh_id"), x["status"]]
            for x in r["only_parakh"]], {1: 30})
    return _save(wb), "UDISE_APAAR_PARAKH_report.xlsx"


def teacher_report(teacher) -> Tuple[bytes, str]:
    """A teacher's own students only (their PARAKH classes, from the register)."""
    mine = school_register.for_teacher(teacher)
    ids = {r["id"] for r in mine}
    reg, entered, session = _students(teacher.school_id)
    rows = [s for s in reg if s["id"] in ids]
    wb = _book()
    counts = {k: sum(1 for s in rows if (s.get("card") or {}).get("status") == k) for k in register_status.ORDER}
    _sheet(wb, "Summary", ["", "Students"], [["My students", len(rows)], *[[k, v] for k, v in counts.items() if v]], {1: 30})
    _sheet(wb, "My students", STUDENT_HEADS, [_row(s, entered.get(s["id"]) or {}) for s in rows], {4: 32, 12: 40})
    pending = [s for s in rows if (s.get("card") or {}).get("status") not in ("Verified on PARAKH",)]
    _sheet(wb, "Pending", STUDENT_HEADS, [_row(s, entered.get(s["id"]) or {}) for s in pending], {4: 32, 12: 40})
    return _save(wb), f"My_students_{session or ''}.xlsx"
