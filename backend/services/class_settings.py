"""
Class settings set once on the dashboard, per teacher and stage (replaces the old workbook's seeder
sheet): medium of instruction, rural/urban, working days per month, max summative marks per subject,
and the declaration. They fill those fields for every student; a per-student exception is made in the
workbook's Exceptions sheet. The academic year, grade and section come from PARAKH and are not set here.

values = {"medium": "English", "rural_urban": "Rural", "working_days": [22, 23, ... 12 numbers],
          "max_marks": {"1": 33, "2": 33, ...}, "declaration": "Yes"}
"""
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from backend.database import SessionLocal
from backend.hpc import credit
from backend.hpc.stages.common import MONTH_DAYS, MONTH_NAMES, MONTHS
from backend.models.settings import ClassSetting
from backend.services import audit

UNUSUAL_DAYS = 26


def marks_subjects(stage: str) -> List[Tuple[str, str]]:
    """(number used in the workbook key d_<n>_max, subject name) for subjects with summative marks."""
    return credit.summative_subjects(stage)


def blank(stage: str) -> Dict[str, Any]:
    return {"medium": "", "rural_urban": "", "working_days": [None] * 12,
            "max_marks": {n: None for n, _ in marks_subjects(stage)}, "declaration": ""}


def validate(stage: str, values: Dict[str, Any], medium_options: Optional[List[str]] = None,
             location_options: Optional[List[str]] = None) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
    """(cleaned values, problems by field, warnings by field). Blank is allowed while setting up."""
    clean, problems, warnings = blank(stage), {}, {}
    for key, options in (("medium", medium_options), ("rural_urban", location_options)):
        v = str(values.get(key) or "").strip()
        if v and options and v not in options:
            problems[key] = f"Choose one of: {', '.join(options)}."
        clean[key] = v
    days = list(values.get("working_days") or []) + [None] * 12
    for i, month in enumerate(MONTHS):
        raw = days[i]
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        if not text.lstrip("-").isdigit():
            problems[f"working_days.{i}"] = f"{MONTH_NAMES[month]}: use a whole number."
            continue
        n = int(text)
        if n < 0 or n > MONTH_DAYS[month]:
            problems[f"working_days.{i}"] = f"{MONTH_NAMES[month]}: between 0 and {MONTH_DAYS[month]}."
            continue
        if n == 0 or n > UNUSUAL_DAYS:
            warnings[f"working_days.{i}"] = f"{MONTH_NAMES[month]}: {n} working days is unusual - please check."
        clean["working_days"][i] = n
    given = values.get("max_marks") or {}
    for n, subject in marks_subjects(stage):
        raw = given.get(n, given.get(int(n)) if isinstance(given, dict) else None)
        if raw in (None, ""):
            continue
        try:
            m = float(str(raw).strip())
        except ValueError:
            m = math.nan
        if not math.isfinite(m):                          # 'nan', 'inf' (H-7)
            problems[f"max_marks.{n}"] = f"{subject}: use a number."
            continue
        if m <= 0:
            problems[f"max_marks.{n}"] = f"{subject}: must be more than 0."
            continue
        clean["max_marks"][n] = int(m) if m.is_integer() else m
    d = str(values.get("declaration") or "").strip()
    if d and d not in ("Yes", "No"):
        problems["declaration"] = "Choose Yes or No."
    clean["declaration"] = d
    return clean, problems, warnings


def missing(stage: str, values: Dict[str, Any]) -> List[str]:
    """What still has to be set before the workbook can be generated, in plain words."""
    out = []
    if not values.get("medium"):
        out.append("Medium of instruction")
    if not values.get("rural_urban"):
        out.append("Rural / Urban")
    gaps = [MONTH_NAMES[m] for m, d in zip(MONTHS, values.get("working_days") or [None] * 12) if d is None]
    if gaps:
        out.append("Working days for " + ", ".join(gaps))
    gaps = [s for n, s in marks_subjects(stage) if (values.get("max_marks") or {}).get(n) is None]
    if gaps:
        out.append("Max marks for " + ", ".join(gaps))
    if not values.get("declaration"):
        out.append("Declaration")
    return out


def row_values(stage: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """The workbook-row values the settings give every student (before that student's exceptions)."""
    out: Dict[str, Any] = {"a1_medium": values.get("medium", ""), "a1_rural_urban": values.get("rural_urban", "")}
    for i, d in enumerate(values.get("working_days") or []):
        out[f"a1_working_{i + 1}"] = "" if d is None else d
    for n, _ in marks_subjects(stage):
        m = (values.get("max_marks") or {}).get(n)
        out[f"d_{n}_max"] = "" if m is None else m
    out["d_declaration"] = values.get("declaration", "")
    return out


SETTING_KEYS = {"a1_medium", "a1_rural_urban", "d_declaration"} | {f"a1_working_{i}" for i in range(1, 13)}


def is_setting_key(key: str) -> bool:
    return key in SETTING_KEYS or (key.startswith("d_") and key.endswith("_max"))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load(teacher_id: str, stage: str) -> Optional[ClassSetting]:
    with SessionLocal() as db:
        row = db.query(ClassSetting).filter_by(teacher_id=teacher_id, stage=stage).first()
        if row:
            db.expunge(row)
        return row


def view(stage: str, row: Optional[ClassSetting]) -> Dict[str, Any]:
    values = row.values if row else blank(stage)
    return {"stage": stage, "values": values, "missing": missing(stage, values), "complete": not missing(stage, values),
            "version": row.version if row else 0,
            "updated_at": row.updated_at.isoformat(timespec="seconds") + "Z" if row and row.updated_at else None,
            "marks_subjects": [{"n": n, "name": s} for n, s in marks_subjects(stage)],
            "months": [{"key": m, "name": MONTH_NAMES[m], "max": MONTH_DAYS[m]} for m in MONTHS]}


def save(teacher, stage: str, values: Dict[str, Any], version: Optional[int], medium_options=None,
         location_options=None) -> Dict[str, Any]:
    clean, problems, warnings = validate(stage, values, medium_options, location_options)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"problems": problems, "warnings": warnings})
    with SessionLocal() as db:
        row = db.query(ClassSetting).filter_by(teacher_id=teacher.id, stage=stage).first()
        if version is not None and version != (row.version if row else 0):
            raise HTTPException(status.HTTP_409_CONFLICT, "These settings were changed in another window. Reload them first.")
        before = dict(row.values) if row else None
        if row is None:
            row = ClassSetting(school_id=teacher.school_id, teacher_id=teacher.id, stage=stage, values=clean, version=1)
            db.add(row)
        else:
            row.values, row.version = clean, row.version + 1
        row.updated_by, row.updated_at = f"teacher:{teacher.id}", datetime.utcnow()
        db.commit()
        db.refresh(row)
        db.expunge(row)
    audit.record(f"teacher:{teacher.id}", "save_class_settings", "class_settings", stage, before, clean)
    return {**view(stage, row), "warnings": warnings}
