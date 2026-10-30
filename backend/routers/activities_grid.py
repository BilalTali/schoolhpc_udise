"""
The teacher's Activities grid (see services/activity_grid.py).

  GET  /teacher/activities-grid/{stage}?refresh=false        every fetched student with their grid values
  PUT  /teacher/activities-grid/{stage}/{student_id}         autosave one student's values
  POST /teacher/activities-grid/{stage}/quick-fill           fill many cells (preview first, then apply)
  POST /teacher/activities-grid/{stage}/import-upload        bring in an old-layout workbook's activity columns
"""
import json
import shutil
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.hpc import workbook
from backend.hpc.portal import PortalError
from backend.models.entities import Teacher
from backend.routers.teachers import _portal, _roster_file, _stage, _upload_path
from backend.services import activity_grid
from backend.services.auth_service import require_teacher

router = APIRouter(prefix="/teacher/activities-grid", tags=["Activities grid"])


class SaveRequest(BaseModel):
    values: Dict[str, Optional[str]] = Field(..., description="grid keys -> value; empty clears a choice")
    base_version: Optional[int] = Field(None, description="the draft version this edit started from")


class QuickFillRequest(BaseModel):
    activity_key: str = Field("", description="library key, e.g. P85; \"each_subject\" = every subject its own activity for the student's grade; empty = only set levels")
    subjects: Optional[List[str]] = Field(None, description="subject codes; leave out for all subjects")
    students: Optional[List[str]] = Field(None, description="student ids; leave out for every student shown")
    grade: Optional[str] = Field(None, description="'Grade 4 - A': only that grade and section")
    levels: Dict[Literal["awareness", "sensitivity", "creativity"], str] = Field(default_factory=dict)
    replace_filled: bool = False
    replace_on_parakh: bool = Field(False, description="tick 'Replace activities on PARAKH' for the students filled")
    apply: bool = False
    expected_cells: Optional[int] = Field(None, description="the cell count the preview showed (apply only)")
    mix_seed: Optional[str] = Field(None, max_length=32, description="the seed the preview returned (Mixed levels)")


class ImportRequest(BaseModel):
    file_name: str = Field(..., description="the workbook uploaded on 'Validate & Upload'")
    apply: bool = False
    expected_cells: Optional[int] = None


def _students(teacher: Teacher, stage: str) -> List[dict]:
    path = _roster_file(teacher, stage)
    students = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not students:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {stage} students yet. Use 'Fetch from PARAKH' on the roster first.")
    return students


def _call(fn, *args):
    try:
        return fn(*args)
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/{stage}")
def get_grid(stage: str, refresh: bool = False, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    return _call(activity_grid.load, _portal(teacher), teacher, stage, _students(teacher, stage), refresh)


@router.put("/{stage}/{student_id}")
def save_student(stage: str, student_id: str, payload: SaveRequest, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    student = next((s for s in _students(teacher, stage) if s["student_id"] == student_id), None)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This student is not in your class list.")
    return _call(activity_grid.save, _portal(teacher), teacher, stage, student, payload.values, payload.base_version)


@router.post("/{stage}/import-upload")
def import_upload(stage: str, payload: ImportRequest, teacher: Teacher = Depends(require_teacher)):
    """Activity choices from an uploaded old-layout workbook. The file is backed up before anything is applied."""
    stage = _stage(teacher, stage)
    path = _upload_path(teacher, payload.file_name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload the file on 'Validate & Upload' first.")
    # files from before the multi-stage workbook have no Stage column: they hold one stage only
    rows = {sid: r for sid, r in workbook.read(path).items() if r.get(workbook.STAGE_KEY) in (stage, None, "")}
    if payload.apply:
        backups = path.parent / "backups"
        backups.mkdir(exist_ok=True)
        shutil.copy2(path, backups / f"{datetime.now():%Y%m%d_%H%M%S}_{path.name}")
    return _call(activity_grid.import_old_layout, _portal(teacher), teacher, stage, _students(teacher, stage), rows,
                 payload.apply, payload.expected_cells)


@router.post("/{stage}/quick-fill")
def quick_fill(stage: str, payload: QuickFillRequest, teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    students = _students(teacher, stage)
    if payload.students is not None:
        wanted = set(payload.students)
        students = [s for s in students if s["student_id"] in wanted]
    if payload.grade:
        students = [s for s in students if f"{s.get('grade', '')} - {s.get('section', '')}".strip(" -") == payload.grade]
    if not students:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No students match. Choose a grade or tick some students.")
    return _call(activity_grid.quick_fill, _portal(teacher), teacher, stage, students, payload.activity_key,
                 payload.subjects, dict(payload.levels), payload.replace_filled, payload.apply, payload.expected_cells,
                 payload.replace_on_parakh, payload.mix_seed)
