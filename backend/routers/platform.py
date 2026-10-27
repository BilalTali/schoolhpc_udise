"""
The application admin's endpoints: every school and teacher, a platform dashboard, the audit trail, and the
activities offered to every school (shared by teachers, or made by the application admin).

Nothing here reads students' records or PARAKH passwords.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.entities import PlatformAdmin, School, StudentRecord, Teacher, UploadJob
from backend.models.library import AuditLog, LibraryActivity
from backend.services import audit
from backend.services.auth_service import end_all_sessions, hash_password, require_app_admin

router = APIRouter(prefix="/platform", tags=["Application admin"])


class ActiveRequest(BaseModel):
    is_active: bool


class PasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, description="New password (min 8 characters)")


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def _record(admin: PlatformAdmin, action: str, entity: str, entity_id: str, after=None, school_id=None) -> None:
    audit.record(f"app_admin:{admin.id}", action, entity, entity_id, None, after, school_id=school_id)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/stats")
def stats(admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Totals across every school."""
    by_status = dict(db.query(StudentRecord.status, func.count()).group_by(StudentRecord.status).all())
    return {
        "schools": db.query(School).count(), "schools_active": db.query(School).filter(School.is_active == True).count(),  # noqa: E712
        "teachers": db.query(Teacher).count(), "teachers_active": db.query(Teacher).filter(Teacher.is_active == True).count(),  # noqa: E712
        "uploads": db.query(UploadJob).count(),
        "cards_saved": by_status.get("SUCCESS", 0), "cards_failed": by_status.get("FAILED", 0) + by_status.get("INVALID", 0),
        "last_upload_at": _iso(db.query(func.max(UploadJob.created_at)).scalar()),
        "activities_waiting": db.query(LibraryActivity).filter(LibraryActivity.share_state == "community").count(),
        "activities_offered": db.query(LibraryActivity).filter(LibraryActivity.share_state == "community_ok").count(),
    }


# ---------------------------------------------------------------------------
# Schools and teachers
# ---------------------------------------------------------------------------

def _school_or_404(db: Session, school_id: str) -> School:
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School not found.")
    return school


def _teacher_or_404(db: Session, teacher_id: str) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Teacher not found.")
    return teacher


def _saved_counts(db: Session, teacher_ids):
    """teacher id -> (cards saved to PARAKH, cards not saved, last upload)."""
    if not teacher_ids:
        return {}
    rows = (db.query(UploadJob.teacher_id, StudentRecord.status, func.count())
            .join(StudentRecord, StudentRecord.job_id == UploadJob.id)
            .filter(UploadJob.teacher_id.in_(teacher_ids)).group_by(UploadJob.teacher_id, StudentRecord.status).all())
    last = dict(db.query(UploadJob.teacher_id, func.max(UploadJob.created_at))
                .filter(UploadJob.teacher_id.in_(teacher_ids)).group_by(UploadJob.teacher_id).all())
    out = {t: [0, 0, last.get(t)] for t in teacher_ids}
    for t, st, n in rows:
        if st == "SUCCESS":
            out[t][0] += n
        elif st in ("FAILED", "INVALID"):
            out[t][1] += n
    return out


@router.get("/schools")
def schools(admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Every school with its teachers and progress."""
    all_schools = db.query(School).order_by(School.school_name).all()
    teachers = db.query(Teacher).all()
    counts = _saved_counts(db, [t.id for t in teachers])
    out = []
    for s in all_schools:
        mine = [t for t in teachers if t.school_id == s.id]
        lasts = [counts[t.id][2] for t in mine if counts[t.id][2]]
        out.append({"id": s.id, "udise_code": s.udise_code, "school_name": s.school_name, "district": s.district,
                    "state": s.state, "admin_email": s.admin_email, "is_active": bool(s.is_active),
                    "teachers": len(mine), "teachers_active": sum(1 for t in mine if t.is_active),
                    "cards_saved": sum(counts[t.id][0] for t in mine), "cards_failed": sum(counts[t.id][1] for t in mine),
                    "last_upload_at": _iso(max(lasts)) if lasts else None, "registered_at": _iso(s.created_at)})
    return out


@router.get("/schools/{school_id}/teachers")
def school_teachers(school_id: str, admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    _school_or_404(db, school_id)
    mine = db.query(Teacher).filter(Teacher.school_id == school_id).order_by(Teacher.teacher_name).all()
    counts = _saved_counts(db, [t.id for t in mine])
    return [{"id": t.id, "teacher_name": t.teacher_name, "username": t.username, "stages": t.stages,
             "is_active": bool(t.is_active), "last_login": _iso(t.last_login),
             "cards_saved": counts[t.id][0], "cards_failed": counts[t.id][1], "last_upload_at": _iso(counts[t.id][2])}
            for t in mine]


@router.put("/schools/{school_id}")
def set_school_active(school_id: str, payload: ActiveRequest, admin: PlatformAdmin = Depends(require_app_admin),
                      db: Session = Depends(get_db)):
    """Switching a school off signs out its admin and every teacher of it."""
    school = _school_or_404(db, school_id)
    school.is_active = payload.is_active
    if not payload.is_active:
        end_all_sessions(db, school)
        for t in db.query(Teacher).filter(Teacher.school_id == school.id).all():
            end_all_sessions(db, t)
    db.commit()
    _record(admin, "switch_school_on" if payload.is_active else "switch_school_off", "school", school.id, school_id=school.id)
    return {"id": school.id, "is_active": bool(school.is_active)}


@router.put("/teachers/{teacher_id}")
def set_teacher_active(teacher_id: str, payload: ActiveRequest, admin: PlatformAdmin = Depends(require_app_admin),
                       db: Session = Depends(get_db)):
    teacher = _teacher_or_404(db, teacher_id)
    teacher.is_active = payload.is_active
    if not payload.is_active:
        end_all_sessions(db, teacher)
    db.commit()
    _record(admin, "switch_teacher_on" if payload.is_active else "switch_teacher_off", "teacher", teacher.id,
            school_id=teacher.school_id)
    return {"id": teacher.id, "is_active": bool(teacher.is_active)}


@router.post("/schools/{school_id}/password")
def set_school_password(school_id: str, payload: PasswordRequest, admin: PlatformAdmin = Depends(require_app_admin),
                        db: Session = Depends(get_db)):
    """A new password for a school admin who forgot theirs; their old sessions end."""
    school = _school_or_404(db, school_id)
    school.hashed_password = hash_password(payload.password)
    end_all_sessions(db, school)
    _record(admin, "set_school_password", "school", school.id, school_id=school.id)      # never the password
    return {"success": True}


@router.post("/teachers/{teacher_id}/password")
def set_teacher_password(teacher_id: str, payload: PasswordRequest, admin: PlatformAdmin = Depends(require_app_admin),
                         db: Session = Depends(get_db)):
    teacher = _teacher_or_404(db, teacher_id)
    teacher.hashed_password = hash_password(payload.password)
    end_all_sessions(db, teacher)
    _record(admin, "set_teacher_password", "teacher", teacher.id, school_id=teacher.school_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@router.get("/audit")
def audit_trail(school_id: Optional[str] = None, action: Optional[str] = None, limit: int = Query(200, ge=1, le=1000),
                admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Who changed what and when, newest first (UDID and guardian names are never stored, M-7)."""
    q = db.query(AuditLog)
    if school_id:
        q = q.filter(AuditLog.school_id == school_id)
    if action:
        q = q.filter(AuditLog.action == action)
    names = {s.id: s.school_name for s in db.query(School).all()}
    return [{"at": _iso(r.at), "actor": r.actor, "school": names.get(r.school_id, ""), "school_id": r.school_id,
             "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "before": r.before, "after": r.after}
            for r in q.order_by(AuditLog.at.desc()).limit(limit).all()]


# ---------------------------------------------------------------------------
# Activities offered to every school
# ---------------------------------------------------------------------------

def _activity(db: Session, activity_id: str) -> LibraryActivity:
    act = db.get(LibraryActivity, activity_id)
    if not act or act.source != "local":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found.")
    return act


@router.get("/activities")
def activities(admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Teachers' activities waiting to be offered to every school, those already offered, and the application
    admin's own (offered or not yet)."""
    rows = (db.query(LibraryActivity).filter(LibraryActivity.source == "local")
            .filter((LibraryActivity.share_state.in_(("community", "community_ok"))) | (LibraryActivity.owner_school_id.is_(None)))
            .order_by(LibraryActivity.stage, LibraryActivity.title).all())
    names = {s.id: s.school_name for s in db.query(School).all()}
    from backend.services.activity_library import STAGE_GRADES, _subject_names
    return [{"id": a.id, "title": a.title, "stage": a.stage, "grade": STAGE_GRADES.get(a.stage, {}).get(a.grade_id, ""),
             "subjects": [_subject_names(a.stage).get(c, c) for c in (a.subjects or [])],
             "made_by": "Application admin" if a.owner_school_id is None else names.get(a.owner_school_id, "a school"),
             "state": {"community": "waiting", "community_ok": "offered"}.get(a.share_state, "not offered"),
             "updated_at": _iso(a.updated_at)} for a in rows]


@router.post("/activities/{activity_id}/offer")
def offer(activity_id: str, admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Offers an activity to every school: a teacher's shared one after review, or one the application admin made."""
    act = _activity(db, activity_id)
    if act.owner_school_id is not None and act.share_state != "community":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only activities a teacher shared with other schools can be offered.")
    act.share_state = "community_ok"
    db.commit()
    _record(admin, "offer_activity", "activity", act.id, {"share_state": "community_ok"})
    return {"id": act.id, "state": "offered"}


@router.post("/activities/{activity_id}/withdraw")
def withdraw(activity_id: str, admin: PlatformAdmin = Depends(require_app_admin), db: Session = Depends(get_db)):
    """Stops offering it to other schools (a teacher's goes back to their own school; it is not deleted)."""
    act = _activity(db, activity_id)
    act.share_state = "private" if act.owner_school_id is None else "school"
    db.commit()
    _record(admin, "withdraw_activity", "activity", act.id, {"share_state": act.share_state})
    return {"id": act.id, "state": "not offered"}
