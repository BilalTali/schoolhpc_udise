"""
Teacher endpoints for working on HPC cards in the web app (instead of, or next to, the workbook).

  GET    /teacher/sessions                                   academic sessions (current one for now)
  GET    /teacher/hpc-cards/{stage}/fields                   parts and fields of a stage
  GET    /teacher/hpc-cards/{stage}/{student_id}             the form: values, draft, per-part status
  PUT    /teacher/hpc-cards/{stage}/{student_id}/draft       autosave (merges into the server draft)
  DELETE /teacher/hpc-cards/{stage}/{student_id}/draft       discard the draft
  POST   /teacher/hpc-cards/{stage}/{student_id}/submit      save to the portal and mark complete
  GET    /teacher/hpc-cards/{stage}/{student_id}/preview     read-only card for print
  GET    /teacher/hpc-cards/{stage}/bulk?field=<key>         one field for the whole class
  PUT    /teacher/hpc-cards/{stage}/bulk                     set that field for many students (drafts)
Every endpoint takes ?session=<code> (default: the current session). Past sessions are read-only.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.hpc.portal import PortalError
from backend.models.entities import Teacher
from backend.routers.teachers import _portal, _stage, teacher_stages
from backend.services import hpc_cards
from backend.services.auth_service import require_teacher

router = APIRouter(prefix="/teacher", tags=["HPC cards"])


class DraftRequest(BaseModel):
    values: Dict[str, Any] = Field(..., description="field key -> value (a list for multi-choice fields)")
    base_version: Optional[int] = Field(None, description="the draft version this edit started from")


class BulkRequest(BaseModel):
    field: str
    values: Dict[str, Any] = Field(..., description="student_id -> value")


def _ctx(teacher: Teacher, stage: str, session: Optional[str], writing: bool = False):
    client = _portal(teacher)
    return client, _stage(teacher, stage), hpc_cards.check_session(client, session, writing)


def _portal_call(fn, *args):
    try:
        return fn(*args)
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/sessions")
def sessions(background_tasks: BackgroundTasks, teacher: Teacher = Depends(require_teacher)):
    """Also warms the dropdown lists for the teacher's stages (about 9 s each, cached 30 min)."""
    client = _portal(teacher)
    for stage in teacher_stages(teacher):
        background_tasks.add_task(_warm, f"teacher_{teacher.id}", client, stage)
    return {"sessions": hpc_cards.academic_sessions(client)}


def _warm(owner, client, stage):
    try:
        hpc_cards.lookups_for(owner, client, stage)
    except Exception:
        pass            # warming is best effort; the next real request loads them anyway


@router.get("/hpc-cards/{stage}/fields")
def fields(stage: str, common: bool = False, teacher: Teacher = Depends(require_teacher)):
    client, stage = _portal(teacher), _stage(teacher, stage)
    return {"stage": stage, "parts": _portal_call(lambda: hpc_cards.stage_fields(
        stage, hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage), common))}


@router.get("/hpc-cards/{stage}/bulk")
def bulk_read(stage: str, field: str = Query(...), session: Optional[str] = None,
              teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session)
    return _portal_call(hpc_cards.bulk_read, client, f"teacher_{teacher.id}", teacher.id, session, stage, field)


@router.put("/hpc-cards/{stage}/bulk")
def bulk_write(stage: str, payload: BulkRequest, session: Optional[str] = None,
               teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session, writing=True)
    return _portal_call(hpc_cards.bulk_write, client, f"teacher_{teacher.id}", teacher.id, session, stage,
                        payload.field, payload.values)


@router.get("/hpc-cards/{stage}/{student_id}")
def get_card(stage: str, student_id: str, session: Optional[str] = None, teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session)
    return _portal_call(hpc_cards.card, client, f"teacher_{teacher.id}", teacher.id, session, stage, student_id)


@router.put("/hpc-cards/{stage}/{student_id}/draft")
def save_draft(stage: str, student_id: str, payload: DraftRequest, session: Optional[str] = None,
               teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session, writing=True)
    lookups = _portal_call(hpc_cards.lookups_for, f"teacher_{teacher.id}", client, stage)
    problems = hpc_cards.validate_values(stage, lookups, payload.values)
    if any(v == "Unknown field." for v in problems.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"problems": problems})
    draft = hpc_cards.save_draft(teacher.id, session, stage, student_id, payload.values, payload.base_version)
    return {"version": draft["version"], "saved_at": draft["saved_at"], "problems": problems}


@router.delete("/hpc-cards/{stage}/{student_id}/draft")
def discard_draft(stage: str, student_id: str, session: Optional[str] = None,
                  teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session, writing=True)
    hpc_cards.delete_draft(teacher.id, session, stage, student_id)
    return {"success": True}


@router.post("/hpc-cards/{stage}/{student_id}/submit")
def submit(stage: str, student_id: str, session: Optional[str] = None, teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session, writing=True)
    return _portal_call(hpc_cards.submit, client, f"teacher_{teacher.id}", teacher.id, session, stage, student_id)


@router.get("/hpc-cards/{stage}/{student_id}/preview")
def preview(stage: str, student_id: str, session: Optional[str] = None, include_draft: bool = True,
            teacher: Teacher = Depends(require_teacher)):
    client, stage, session = _ctx(teacher, stage, session)
    return _portal_call(hpc_cards.preview, client, f"teacher_{teacher.id}", teacher.id, session, stage, student_id,
                        include_draft)
