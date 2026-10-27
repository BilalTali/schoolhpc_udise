"""
Activity Library endpoints (school admin and teachers; see services/activity_library.py for the rules).

  GET    /activity-library?stage=...&q&source&subject&covers_all&status&edited&upstream&mine&page&page_size
  GET    /activity-library/{id}                 one activity, with the original and a diff
  POST   /activity-library                      new activity made in this app
  PATCH  /activity-library/{id}                 texts, subjects, display name, on/off
  POST   /activity-library/{id}/reset           back to the PARAKH original
  POST   /activity-library/{id}/duplicate
  POST   /activity-library/{id}/share           private | school | community (needs consent)
  DELETE /activity-library/{id}                 activities made in this app only
  POST   /activity-library/bulk                 turn many on or off
  GET    /activity-library/defaults/{stage}
  PUT    /activity-library/defaults/{stage}
  GET    /activity-library/dropdown/{stage}     what the workbook dropdown will offer
  POST   /activity-library/sync                 start a read-only sync from PARAKH
  GET    /activity-library/sync/status          latest sync and last sync time per stage
  GET    /activity-library/sync/{job_id}
"""
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.entities import School, Teacher
from backend.models.library import ActivitySyncJob
from backend.services import activity_library as lib
from backend.services import hpc_sessions
from backend.services.auth_service import get_current_user

router = APIRouter(prefix="/activity-library", tags=["Activity Library"])


def _actor(current_user: Dict[str, Any] = Depends(get_current_user)) -> lib.Actor:
    return lib.actor_from(current_user)


class Rubric(BaseModel):
    beginner: Optional[str] = None
    proficient: Optional[str] = None
    advanced: Optional[str] = None


class ActivityTexts(BaseModel):
    activity_text: Optional[str] = Field(None, description="How the activity is done (PARAKH: description 1)")
    assessment_text: Optional[str] = Field(None, description="How it is assessed (PARAKH: description 2)")
    rubric: Optional[Dict[Literal["awareness", "sensitivity", "creativity"], Rubric]] = None
    goals: Optional[List[str]] = None
    competencies: Optional[List[str]] = None
    grade_id: Optional[int] = Field(None, description="PARAKH grade id within the stage (activities made here)")
    subjects: Optional[List[str]] = Field(None, description="subject codes of the stage, e.g. PSLS1")
    approaches: Optional[List[int]] = Field(None, description="Middle: 1 Art, 2 Sports, 3 Toy, 4 Technology, 5 Any other")
    approach_other: Optional[str] = None

    def changes(self) -> Dict[str, Any]:
        out = self.model_dump(exclude_none=True, exclude={"rubric"})
        if self.rubric:
            out["rubric"] = {a: r.model_dump(exclude_none=True) for a, r in self.rubric.items()}
        return out


class CreateRequest(ActivityTexts):
    stage: str
    title: str
    share: Optional[Literal["private", "school", "community"]] = None
    consent: bool = False


class UpdateRequest(ActivityTexts):
    title: Optional[str] = None
    display_name: Optional[str] = None
    status: Optional[Literal["active", "disabled"]] = None
    version: Optional[int] = Field(None, description="the version this edit started from (to catch two people editing)")


class ShareRequest(BaseModel):
    level: Literal["private", "school", "community"]
    consent: bool = False


class BulkRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=1000)
    action: Literal["enable", "disable"]


class DefaultRequest(BaseModel):
    activity_id: Optional[str] = None
    confirm_partial: bool = False


class SyncRequest(BaseModel):
    stage: Optional[str] = Field(None, description="one stage, or leave out for all stages")


# ---------------------------------------------------------------------------
# Browse
# ---------------------------------------------------------------------------

@router.get("")
def list_activities(stage: str, q: str = "", source: str = "", subject: str = "", covers_all: Optional[bool] = None,
                    status_: str = Query("", alias="status"), edited: Optional[bool] = None, upstream: str = "",
                    mine: Optional[bool] = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                    actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    stage = lib.check_stage(stage)
    views = lib.list_views(db, actor, stage)
    found = lib.filter_views(views, q, source, subject, covers_all, status_, edited, upstream, mine)
    start = (page - 1) * page_size
    return {
        "stage": stage, "subjects": lib.stage_subjects(stage), "total": len(found), "page": page, "page_size": page_size,
        "items": found[start:start + page_size],
        "counts": {"all": len(views), "active": sum(v["status"] == "active" for v in views),
                   "disabled": sum(v["status"] == "disabled" for v in views),
                   "covers_all": sum(v["covers_all"] for v in views), "edited": sum(v["edited"] for v in views),
                   "removed": sum(v["upstream_status"] == "removed" for v in views),
                   "usable_in_excel": sum(v["usable_in_excel"] for v in views)},
        "default_id": lib.default_id(db, actor.school_id, stage),
        "default_label": next((v["label"] for v in views if v["is_default"]), None),
        "sync": lib.last_syncs(db, actor.school_id),
        "consent_text": lib.CONSENT_TEXT,
    }


@router.get("/dropdown/{stage}")
def dropdown(stage: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    return {"stage": lib.check_stage(stage), "entries": lib.dropdown_entries(db, actor, lib.check_stage(stage))}


@router.get("/codes/{stage}")
def codes(stage: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    """Goal and competency codes a new activity can use (taken from PARAKH's own activities)."""
    return {"stage": lib.check_stage(stage), **lib.known_codes(db, actor, lib.check_stage(stage))}


@router.get("/defaults/{stage}")
def get_default(stage: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    stage = lib.check_stage(stage)
    return {"stage": stage, "activity_id": lib.default_id(db, actor.school_id, stage)}


@router.put("/defaults/{stage}")
def put_default(stage: str, payload: DefaultRequest, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    result = lib.set_default(db, actor, lib.check_stage(stage), payload.activity_id, payload.confirm_partial)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Sync (read-only against PARAKH)
# ---------------------------------------------------------------------------

@router.get("/sync/status")
def sync_status(actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    return lib.last_syncs(db, actor.school_id)


@router.get("/sync/{job_id}")
def sync_job(job_id: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    job = db.get(ActivitySyncJob, job_id)
    if not job or job.school_id != actor.school_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sync not found.")
    return lib.job_view(job)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def start_sync(payload: SyncRequest, background_tasks: BackgroundTasks, actor: lib.Actor = Depends(_actor),
               db: Session = Depends(get_db)):
    stages = [lib.check_stage(payload.stage)] if payload.stage else list(lib.STAGES)
    client = _client(db, actor)                       # fails here (401) when there is no PARAKH session
    if not actor.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your school admin updates the activities from PARAKH (it also "
                            "happens automatically every day). You always get the latest copy here.")
    job, running = lib.start_sync(db, actor, stages)
    if not running:
        background_tasks.add_task(lib.run_sync, job.id, client, actor, False)
    return {**lib.job_view(job), "already_running": running}


def _client(db: Session, actor: lib.Actor):
    """The school's PARAKH session for admins; a teacher's own session for teachers."""
    if actor.is_admin:
        school = db.get(School, actor.id)
        return hpc_sessions.portal_for("school", school.id, school.hpc_login_id, school.hpc_password)
    teacher = db.get(Teacher, actor.id)
    return hpc_sessions.portal_for("teacher", teacher.id, teacher.hpc_login_id, teacher.hpc_password)


# ---------------------------------------------------------------------------
# One activity
# ---------------------------------------------------------------------------

@router.get("/{activity_id}")
def get_activity(activity_id: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    return lib.detail(db, actor, lib.get_visible(db, actor, activity_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_activity(payload: CreateRequest, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    act = lib.create_local(db, actor, lib.check_stage(payload.stage), payload.title, payload.changes(),
                           payload.share or "", payload.consent)
    db.commit()
    return lib.detail(db, actor, act)


@router.patch("/{activity_id}")
def update_activity(activity_id: str, payload: UpdateRequest, actor: lib.Actor = Depends(_actor),
                    db: Session = Depends(get_db)):
    act = lib.get_visible(db, actor, activity_id)
    changes = payload.changes()
    for key in ("title", "display_name", "status"):
        if getattr(payload, key) is not None:
            changes[key] = getattr(payload, key)
    lib.update(db, actor, act, changes, payload.version)
    db.commit()
    return lib.detail(db, actor, act)


@router.post("/{activity_id}/reset")
def reset_activity(activity_id: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    act = lib.get_visible(db, actor, activity_id)
    lib.reset(db, actor, act)
    db.commit()
    return lib.detail(db, actor, act)


@router.post("/{activity_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_activity(activity_id: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    copy_ = lib.duplicate(db, actor, lib.get_visible(db, actor, activity_id))
    db.commit()
    return lib.detail(db, actor, copy_)


@router.post("/{activity_id}/share")
def share_activity(activity_id: str, payload: ShareRequest, actor: lib.Actor = Depends(_actor),
                   db: Session = Depends(get_db)):
    act = lib.get_visible(db, actor, activity_id)
    lib.set_share(db, actor, act, payload.level, payload.consent)
    db.commit()
    return lib.detail(db, actor, act)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(activity_id: str, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    lib.delete_local(db, actor, lib.get_visible(db, actor, activity_id))
    db.commit()


@router.post("/bulk")
def bulk(payload: BulkRequest, actor: lib.Actor = Depends(_actor), db: Session = Depends(get_db)):
    if not actor.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the school admin can turn activities on or off.")
    new_status = "active" if payload.action == "enable" else "disabled"
    changed = []
    for activity_id in dict.fromkeys(payload.ids):
        act = lib.get_visible(db, actor, activity_id)
        lib.update(db, actor, act, {"status": new_status}, None)
        changed.append(act.id)
    db.commit()
    return {"changed": changed, "status": new_status}
