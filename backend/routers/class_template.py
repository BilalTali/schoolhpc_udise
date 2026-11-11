"""
Class settings and the class template (teacher).

  GET  /teacher/settings/{stage}                       the class settings, what is missing, the dropdown choices
  PUT  /teacher/settings/{stage}                       save them (checked; warnings for unusual values)
  POST /teacher/template/{stage}/check                 read the class from PARAKH (GET only) in the background
  GET  /teacher/template/{stage}/precheck              empty required answers, with where to fix them
  GET  /teacher/template/{stage}/check                 progress, then who is ready and why the others are not
  GET  /teacher/template/{stage}/download?include=ready|all&confirmed=true
"""
import json
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.hpc.portal import PortalError
from backend.models.entities import Teacher
from backend.routers.teachers import _portal, _roster_file, _stage, open_students, teacher_stages
from backend.services import activity_library, class_settings, class_template, hpc_cards, hpc_sessions
from backend.services.auth_service import require_teacher

router = APIRouter(prefix="/teacher", tags=["Class settings and template"])


class SettingsRequest(BaseModel):
    values: Dict[str, Any] = Field(..., description="medium, rural_urban, working_days[12], max_marks{n}, declaration")
    version: Optional[int] = None


def _choices(teacher: Teacher, stage: str):
    """Medium and rural/urban choices from PARAKH's lists (cached); empty when PARAKH is not connected."""
    try:
        lk = hpc_cards.lookups_for(f"teacher_{teacher.id}", _portal(teacher), stage)
    except (HTTPException, PortalError):
        return None, None
    return list(lk.options(lk.medium)), list(lk.options(lk.location))


@router.get("/settings/{stage}")
def get_settings(stage: str, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    medium, location = _choices(teacher, stage)
    return {**class_settings.view(stage, class_settings.load(teacher.id, stage), teacher.school_id),
            "choices": {"medium": medium or [], "rural_urban": location or [],
                        "loaded": medium is not None}}


@router.put("/settings/{stage}")
def put_settings(stage: str, payload: SettingsRequest, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    medium, location = _choices(teacher, stage)
    return class_settings.save(teacher, stage, payload.values, payload.version, medium, location)


def _students(teacher: Teacher, stage: str):
    path = _roster_file(teacher, stage)
    students = open_students(path)
    if not students:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {stage} students yet. Use 'Fetch from PARAKH' on the roster first.")
    return students


@router.post("/template/{stage}/check")
def start_check(stage: str, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    students = _students(teacher, stage)
    client = _portal(teacher)
    try:
        lookups = hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage)
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    resolve = hpc_cards._resolver(teacher.id, stage, lookups)
    job = class_template.start_check(client, teacher, stage, students, resolve, lookups)
    return class_template.job_view(job)


@router.get("/template/{stage}/precheck")
def precheck(stage: str, teacher: Teacher = Depends(require_teacher)):
    """Before the check: every empty required answer, grouped by question, with where to fix it (read-only)."""
    stage = _stage(teacher, stage)
    students = _students(teacher, stage)
    client = _portal(teacher)
    try:
        lookups = hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage)
        return class_template.precheck(client, teacher, stage, students, hpc_cards._resolver(teacher.id, stage, lookups))
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/template/{stage}/check")
def check_status(stage: str, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    settings = class_settings.view(stage, class_settings.load(teacher.id, stage), teacher.school_id)
    path = _roster_file(teacher, stage)
    students = len(open_students(path))
    job = class_template.latest(teacher.id, stage)
    return {"job": class_template.job_view(job),
            "settings_complete": settings["complete"], "settings_missing": settings["missing"], "students": students,
            "register_changed": _register_changed_since(teacher, job)}


def _register_changed_since(teacher: Teacher, job) -> bool:
    """True when the school changed the School Register after this check finished: its result is out of date."""
    from datetime import datetime
    from backend.services import register_data
    if not job or not job.get("finished_at"):
        return False
    try:
        changed = register_data.last_change(teacher.school_id)
        finished = datetime.fromisoformat(job["finished_at"]).replace(tzinfo=None)    # both UTC
    except Exception:
        return False
    return bool(changed and changed > finished)


def _labels(teacher: Teacher, stage: str) -> Dict[str, str]:
    actor = activity_library.Actor("TEACHER", teacher.id, teacher.school_id, teacher.teacher_name)
    from backend.database import SessionLocal
    with SessionLocal() as db:
        labels = {e["key"]: e["label"] for e in activity_library.library_entries(db, actor, stage).values()}
    job = class_template.latest(teacher.id, stage)
    if job and job.get("lookups") is not None and not labels:
        labels = {f"P{i}": job["lookups"].activity_label(i) for i in job["lookups"].activities}
    return labels


@router.get("/template/all/download")
def download_all(include: Literal["ready", "all"] = "ready", confirmed: bool = False,
                 teacher: Teacher = Depends(require_teacher)):
    """One Excel file for all the teacher's stages that have students: a sheet per stage."""
    if include == "all" and not confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm first: students who are not ready will be in the file.")
    stages = [st for st in teacher_stages(teacher) if _roster_file(teacher, st).exists()
              and open_students(_roster_file(teacher, st))]
    if not stages:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No students yet. Use 'Fetch from PARAKH' on the Students page first.")
    path = hpc_sessions.session_dir("teacher", teacher.id) / f"HPC_All_stages_template{'_all' if include == 'all' else ''}.xlsx"
    class_template.build_download_many(teacher, stages, include == "all", path, {st: _labels(teacher, st) for st in stages})
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/template/{stage}/download")
def download(stage: str, include: Literal["ready", "all"] = "ready", confirmed: bool = False,
             students: Optional[str] = Query(None, max_length=20000), teacher: Teacher = Depends(require_teacher)):
    """students: comma-separated ids - a file with just those (the teacher picked them, ready or not)."""
    stage = _stage(teacher, stage)
    only = {s.strip() for s in students.split(",") if s.strip()} if students else None
    if include == "all" and not confirmed and only is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm first: students who are not ready will be in the file.")
    tail = "_chosen" if only is not None else "_all" if include == "all" else ""
    path = hpc_sessions.session_dir("teacher", teacher.id) / f"HPC_{stage}_template{tail}.xlsx"
    class_template.build_download(teacher, stage, include == "all", path, _labels(teacher, stage), only)
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class _Range(BaseModel):
    low: float = Field(..., ge=0)
    high: float = Field(..., ge=0)


class _ParentName(BaseModel):
    relation: Literal["Father", "Mother", "Guardian"] = "Father"
    name: str = Field("", max_length=100)


class FillMissingRequest(BaseModel):
    names: Dict[str, _ParentName] = Field(default_factory=dict)     # PARAKH student id -> whose name, the name
    attendance: Optional[_Range] = None                             # % of each month's working days
    marks: Optional[_Range] = None                                  # marks obtained


@router.post("/template/{stage}/fill-missing")
def fill_missing(stage: str, payload: FillMissingRequest, teacher: Teacher = Depends(require_teacher)):
    """What the class check found missing for the teacher's own students, filled into the School Register - only
    where it is empty: parents' names as typed, days present and marks at random inside a range. Then check again."""
    from backend.services import register_data
    stage = _stage(teacher, stage)
    ids = [str(s["student_id"]) for s in _students(teacher, stage)]
    unknown = [k for k in payload.names if k not in ids]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "These students are not in your class: " + ", ".join(unknown[:5]))
    if not payload.names and payload.attendance is None and payload.marks is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type a name, or choose a range for days present or marks.")
    try:
        return register_data.fill_missing(
            teacher.school_id, stage.capitalize(), ids,
            {k: v.model_dump() for k, v in payload.names.items() if v.name.strip()},
            (payload.attendance.low, payload.attendance.high) if payload.attendance else None,
            (int(payload.marks.low), int(payload.marks.high)) if payload.marks else None, f"teacher:{teacher.id}")
    except register_data.Problem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
