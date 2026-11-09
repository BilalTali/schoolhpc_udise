"""
The school's HPC records: one Excel with everything the app holds of every student's card, for the school's own
records. Built from the app's stored copy of the cards (data/cards/<owner>/<session>/<stage>/<student>.json, kept
up to date whenever a teacher works) - no PARAKH sign-in is needed. The cards hold codes for a few answers (medium,
location, activities); they are put into words with PARAKH's lists as last kept for the school (Lookups.offline),
or, when none were kept yet, with the school's own PARAKH connection when there is one.

One sheet per stage and card part (A1, A2, ..., B, C, Credit), one row per student: PARAKH ID, name, class, section,
the teacher whose copy it is, when it was last read from PARAKH, then every field of that part.
"""
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.database import SessionLocal
from backend.hpc.portal import stage_code
from backend.hpc.stages import get_stage
from backend.hpc.stages.common import Lookups
from backend.models.entities import Teacher
from backend.services import card_store
from backend.services.card_store import RECORD

STAGES = ["Foundational", "Preparatory", "Middle"]


class Problem(Exception):
    """Nothing to put in the file yet (said in plain words)."""


def _owners(school_id: str) -> Dict[str, str]:
    """{card-store owner folder: whose copy it is} for the school's teachers (and the school itself)."""
    with SessionLocal() as db:
        teachers = db.query(Teacher).filter(Teacher.school_id == school_id).all()
        out = {f"teacher_{t.id}": t.teacher_name for t in teachers}
    out[f"school_{school_id}"] = "School"
    return out


def collect(school_id: str) -> Tuple[Optional[str], Dict[str, Dict[str, Dict[str, Any]]]]:
    """(latest session, {stage: {student_id: {"parts", "read_at", "owner"}}}) - the newest copy of each student."""
    owners = _owners(school_id)
    cards = card_store.CARDS_DIR
    sessions = sorted({p.name for o in owners if (cards / o).is_dir() for p in (cards / o).iterdir() if p.is_dir()})
    if not sessions:
        return None, {}
    session = sessions[-1]
    found: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for owner, who in owners.items():
        for stage in STAGES:
            folder = cards / owner / session / stage.lower()
            if not folder.is_dir():
                continue
            for f in folder.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                newest = max((v for v in (data.get("read_at") or {}).values() if v), default="")
                have = found.setdefault(stage, {}).get(f.stem)
                if have is None or newest > have["newest"]:
                    found[stage][f.stem] = {"parts": data.get("parts") or {}, "newest": newest, "owner": who}
    return session, found


def workbook(school_id: str, school_client=None) -> Tuple[bytes, str]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from backend.hpc import sync
    from backend.hpc.xl import grid_sheets, keep_text
    session, found = collect(school_id)
    if not found:
        raise Problem("The app holds no cards for this school yet: they are kept once a teacher opens their class "
                      "(Fetch from PARAKH).")
    wb = Workbook()
    info = wb.active
    info.title = "About"
    notes: List[str] = []
    head = PatternFill("solid", fgColor="0B5FA5")
    sub = PatternFill("solid", fgColor="E2E8F0")
    totals = []
    for stage in [s for s in STAGES if s in found]:
        students = found[stage]
        sample = next(iter(students.values()))["parts"].get(RECORD) or {}
        lookups = Lookups.offline(sample.get("school_id"), stage_code(stage))
        if lookups is None and school_client is not None:
            try:
                lookups = Lookups(school_client, stage_code(stage))
            except Exception:                                        # PARAKH not answering: said below
                lookups = None
        if lookups is None:
            notes.append(f"{stage}: left out - PARAKH's lists for it were never kept. A teacher of {stage} opening "
                         "their class once (or the school connecting to PARAKH) makes them available.")
            continue
        rows = []
        for sid, s in students.items():
            record = s["parts"].get(RECORD) or {}
            data = sync.StudentData(sid, record, s["parts"])
            stu = record.get("stu_info") or {}
            rows.append((sid, stu.get("student_name") or "", lookups.grade_code(stu.get("grade_id")),
                         lookups.section_name(stu.get("section_id")), s["owner"], (s["newest"] or "")[:16].replace("T", " "),
                         sync.to_row(stage, data, lookups)))
        rows.sort(key=lambda r: (str(r[2]), str(r[3]), str(r[1])))
        totals.append(f"{stage}: {len(rows)} students")
        for part in get_stage(stage).PARTS:
            fields = part.fields(lookups)
            ws = wb.create_sheet(f"{stage[:4]} {'Credit' if part.code == 'D' else part.code}")
            lead = ["PARAKH ID", "Student name", "Class", "Section", "Teacher (copy of)", "Last read from PARAKH"]
            ws.cell(row=1, column=1, value=f"{stage} - {part.title}").font = Font(bold=True, color="FFFFFF")
            for c in range(1, len(lead) + len(fields) + 1):
                ws.cell(row=1, column=c).fill = head
            for c, title in enumerate(lead + [f.label for f in fields], start=1):
                cell = ws.cell(row=2, column=c, value=title)
                cell.font, cell.fill = Font(bold=True), sub
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            for r, (sid, name, grade, section, owner, read, values) in enumerate(rows, start=3):
                for c, v in enumerate([sid, name, grade, section, owner, read], start=1):
                    ws.cell(row=r, column=c, value=v)
                for c, f in enumerate(fields, start=len(lead) + 1):
                    v = values.get(f.key, "")
                    ws.cell(row=r, column=c, value=", ".join(map(str, v)) if isinstance(v, (list, tuple)) else v)
            for c in range(1, len(lead) + len(fields) + 1):
                ws.column_dimensions[get_column_letter(c)].width = 28 if c == 2 else 14 if c <= len(lead) else 20
            ws.row_dimensions[2].height = 45
            ws.freeze_panes = "C3"
            ws.auto_filter.ref = f"A2:{get_column_letter(len(lead) + len(fields))}{len(rows) + 2}"
    if not totals:
        raise Problem(" ".join(notes) or "Nothing to put in the file yet.")
    lines = [f"HPC records - academic year {session[:2]}-{session[2:]}" if session and len(session) == 4 else "HPC records",
             f"Made {datetime.now().strftime('%d %b %Y, %H:%M')} from the app's stored copy of the cards (as last read "
             "from PARAKH; a teacher's newer, unsaved changes are not in it).",
             "One sheet per stage and card part, one row per student. " + "; ".join(totals) + "."] + notes
    for i, line in enumerate(lines, start=1):
        info.cell(row=i, column=1, value=line).alignment = Alignment(wrap_text=True)
    info["A1"].font = Font(bold=True, size=13)
    info.column_dimensions["A"].width = 120
    keep_text(wb)
    grid_sheets(wb)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), f"HPC_records_{session or 'current'}.xlsx"
