"""
School admin endpoints: teacher accounts, dashboard stats, the school's HPC session and roster.
"""
import json
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.hpc import sync
from backend.hpc.portal import PortalError, stage_code
from backend.hpc.stages.common import Lookups
from backend.models.entities import School, StudentRecord, Teacher, UploadJob
from backend.schemas.schemas import (
    HpcCaptchaRequest, HpcCredentialsRequest, HpcOtpRequest, HpcSessionStatusResponse, HpcStartSessionRequest,
    TeacherCreateRequest, TeacherResponse, TeacherUpdateRequest,
)
from backend.services import audit, hpc_sessions
from backend.services.auth_service import hash_password, require_school_admin

router = APIRouter(prefix="/school", tags=["School Administration"])


# ---------------------------------------------------------------------------
# Teacher CRUD (Create, Read, Update, Delete)
# ---------------------------------------------------------------------------

@router.get("/teachers", response_model=List[TeacherResponse])
def list_school_teachers(
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Lists all teachers created under this school."""
    teachers = db.query(Teacher).filter(Teacher.school_id == admin.id).order_by(Teacher.created_at.desc()).all()
    results = []
    for t in teachers:
        p_status = hpc_sessions.status_of("teacher", t.id)
        stages_list = [s.strip() for s in (t.assigned_stage or "").split(",") if s.strip()]
        grades_list = [g.strip() for g in (t.assigned_grade or "").split(",") if g.strip()]
        t_dict = {
            "id": t.id,
            "school_id": t.school_id,
            "teacher_name": t.teacher_name,
            "employee_code": t.employee_code,
            "username": t.username,
            "mobile_number": t.mobile_number,
            "assigned_stage": t.assigned_stage or "Preparatory",
            "assigned_stages": stages_list if stages_list else ["Preparatory"],
            "assigned_grade": t.assigned_grade or "Grade 3",
            "assigned_grades": grades_list if grades_list else ["Grade 3"],
            "assigned_section": t.assigned_section or "A",
            "is_active": t.is_active,
            "last_login": t.last_login,
            "parakh_connected": p_status.get("logged_in", False),
            "parakh_user": p_status.get("user"),
            "has_hpc_credentials": bool(t.hpc_login_id and t.hpc_password_encrypted),
        }
        results.append(TeacherResponse(**t_dict))
    return results


@router.post("/teachers", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreateRequest,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """
    Creates a new teacher account under the authenticated school.
    Supports single or multi-stage (e.g. ['Preparatory', 'Middle']), grades, and sections.
    The password is only hashed; it is never stored readable or sent back.
    """
    existing = db.query(Teacher).filter(Teacher.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken. Please choose another username."
        )

    # Resolve multi-selection for stages
    if payload.assigned_stages and len(payload.assigned_stages) > 0:
        stage_str = ", ".join(dict.fromkeys(s.strip() for s in payload.assigned_stages if s.strip()))
    else:
        stage_str = (payload.assigned_stage or "Preparatory").strip()

    # Resolve multi-selection for grades
    if payload.assigned_grades and len(payload.assigned_grades) > 0:
        grade_str = ", ".join(dict.fromkeys(g.strip() for g in payload.assigned_grades if g.strip()))
    else:
        grade_str = (payload.assigned_grade or "Grade 3").strip()

    # Resolve multi-selection for sections
    if payload.assigned_sections and len(payload.assigned_sections) > 0:
        sec_str = ", ".join(dict.fromkeys(sec.strip() for sec in payload.assigned_sections if sec.strip()))
    else:
        sec_str = (payload.assigned_section or "A").strip()

    new_teacher = Teacher(
        school_id=admin.id,
        teacher_name=payload.teacher_name.strip(),
        employee_code=payload.employee_code.strip() if payload.employee_code else None,
        username=payload.username.strip().lower(),
        mobile_number=payload.mobile_number.strip() if payload.mobile_number else None,
        hashed_password=hash_password(payload.password),
        assigned_stage=stage_str,
        assigned_grade=grade_str,
        assigned_section=sec_str,
        is_active=True
    )
    db.add(new_teacher)
    db.commit()
    db.refresh(new_teacher)

    stages_list = [s.strip() for s in stage_str.split(",") if s.strip()]
    grades_list = [g.strip() for g in grade_str.split(",") if g.strip()]

    return TeacherResponse(
        id=new_teacher.id,
        school_id=new_teacher.school_id,
        teacher_name=new_teacher.teacher_name,
        employee_code=new_teacher.employee_code,
        username=new_teacher.username,
        mobile_number=new_teacher.mobile_number,
        assigned_stage=new_teacher.assigned_stage,
        assigned_stages=stages_list,
        assigned_grade=new_teacher.assigned_grade,
        assigned_grades=grades_list,
        assigned_section=new_teacher.assigned_section,
        is_active=new_teacher.is_active,
        last_login=None,
        parakh_connected=False,
        has_hpc_credentials=False,
    )


@router.put("/teachers/{teacher_id}", response_model=TeacherResponse)
def update_teacher(
    teacher_id: str,
    payload: TeacherUpdateRequest,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """
    Updates an existing teacher account under this school.
    Allows changing name, username, password, stages, grades, section, or active status.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id, Teacher.school_id == admin.id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found.")

    if payload.username and payload.username.strip().lower() != teacher.username:
        clean_u = payload.username.strip().lower()
        exists = db.query(Teacher).filter(Teacher.username == clean_u, Teacher.id != teacher.id).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{clean_u}' already taken.")
        teacher.username = clean_u

    if payload.teacher_name is not None:
        teacher.teacher_name = payload.teacher_name.strip()
    if payload.employee_code is not None:
        teacher.employee_code = payload.employee_code.strip() if payload.employee_code else None
    if payload.mobile_number is not None:
        teacher.mobile_number = payload.mobile_number.strip() if payload.mobile_number else None
    if payload.password and len(payload.password) >= 6:
        teacher.hashed_password = hash_password(payload.password)

    if payload.assigned_stages and len(payload.assigned_stages) > 0:
        teacher.assigned_stage = ", ".join(dict.fromkeys(s.strip() for s in payload.assigned_stages if s.strip()))
    elif payload.assigned_stage is not None:
        teacher.assigned_stage = payload.assigned_stage.strip()

    if payload.assigned_grades and len(payload.assigned_grades) > 0:
        teacher.assigned_grade = ", ".join(dict.fromkeys(g.strip() for g in payload.assigned_grades if g.strip()))
    elif payload.assigned_grade is not None:
        teacher.assigned_grade = payload.assigned_grade.strip()

    if payload.assigned_sections and len(payload.assigned_sections) > 0:
        teacher.assigned_section = ", ".join(dict.fromkeys(sec.strip() for sec in payload.assigned_sections if sec.strip()))
    elif payload.assigned_section is not None:
        teacher.assigned_section = payload.assigned_section.strip()

    if payload.is_active is not None:
        teacher.is_active = payload.is_active

    db.commit()
    db.refresh(teacher)

    stages_list = [s.strip() for s in (teacher.assigned_stage or "").split(",") if s.strip()]
    grades_list = [g.strip() for g in (teacher.assigned_grade or "").split(",") if g.strip()]
    p_status = hpc_sessions.status_of("teacher", teacher.id)

    return TeacherResponse(
        id=teacher.id,
        school_id=teacher.school_id,
        teacher_name=teacher.teacher_name,
        employee_code=teacher.employee_code,
        username=teacher.username,
        mobile_number=teacher.mobile_number,
        assigned_stage=teacher.assigned_stage,
        assigned_stages=stages_list,
        assigned_grade=teacher.assigned_grade,
        assigned_grades=grades_list,
        assigned_section=teacher.assigned_section,
        is_active=teacher.is_active,
        last_login=teacher.last_login,
        parakh_connected=p_status.get("logged_in", False),
        parakh_user=p_status.get("user"),
        has_hpc_credentials=bool(teacher.hpc_login_id and teacher.hpc_password_encrypted),
    )


@router.delete("/teachers/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(
    teacher_id: str,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Deletes a teacher under this school."""

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id, Teacher.school_id == admin.id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found.")
    db.delete(teacher)
    db.commit()
    return None


@router.get("/stats")
def get_school_stats(
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Aggregated stats for the school admin dashboard."""
    teachers = db.query(Teacher).filter(Teacher.school_id == admin.id).all()
    teacher_ids = [t.id for t in teachers]

    total_teachers = len(teachers)
    total_jobs = db.query(UploadJob).filter(UploadJob.teacher_id.in_(teacher_ids)).count() if teacher_ids else 0

    student_records = (
        db.query(StudentRecord)
        .join(UploadJob)
        .filter(UploadJob.teacher_id.in_(teacher_ids))
        .all()
    ) if teacher_ids else []

    total_students = len(student_records)
    success_students = sum(1 for s in student_records if s.status == "SUCCESS")
    failed_students = sum(1 for s in student_records if s.status in ("FAILED", "INVALID"))

    return {
        "school_name": admin.school_name,
        "udise_code": admin.udise_code,
        "total_teachers": total_teachers,
        "total_jobs": total_jobs,
        "total_students": total_students,
        "submitted_and_verified": success_students,
        "failed_or_needs_attention": failed_students,
        "completion_rate_percent": int((success_students / total_students * 100)) if total_students > 0 else 0
    }


# ---------------------------------------------------------------------------
# The school's own HPC portal session
# ---------------------------------------------------------------------------

KIND = "school"


@router.get("/hpc/status", response_model=HpcSessionStatusResponse)
def get_school_hpc_status(admin: School = Depends(require_school_admin)):
    result = hpc_sessions.status_of(KIND, admin.id)
    return HpcSessionStatusResponse(
        logged_in=result["logged_in"], user=result.get("user"), school=result.get("school"),
        role=result.get("role"), reason=result.get("reason"), captcha_mode=result.get("captcha_mode", "typed"),
        has_credentials=bool(admin.hpc_login_id and admin.hpc_password_encrypted),
        saved_hpc_login_id=admin.hpc_login_id,
    )


@router.post("/hpc/save-credentials")
def save_school_hpc_credentials(payload: HpcCredentialsRequest, admin: School = Depends(require_school_admin),
                                db: Session = Depends(get_db)):
    admin.hpc_login_id = payload.hpc_login_id.strip()
    admin.hpc_password = payload.hpc_password
    db.commit()
    audit.record(f"school_admin:{admin.id}", "save_parakh_login", "settings", admin.id, None,
                 {"hpc_login_id": admin.hpc_login_id})        # never the password
    return {"success": True, "message": "HPC credentials saved. Click 'Start Session' to connect."}


@router.post("/hpc/start-session")
def start_school_session(payload: HpcStartSessionRequest, admin: School = Depends(require_school_admin)):
    login_id = payload.hpc_login_id or admin.hpc_login_id
    password = payload.hpc_password or admin.hpc_password
    if not login_id or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "HPC credentials not found. Save your HPC Login ID and password first.")
    result = hpc_sessions.start(KIND, admin.id, login_id, password)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "HPC login failed."))
    return result


@router.post("/hpc/verify-captcha")
def verify_school_captcha(payload: HpcCaptchaRequest, admin: School = Depends(require_school_admin)):
    """The answer to the captcha picture from start-session; logs in (or asks for the OTP next)."""
    result = hpc_sessions.verify_captcha(KIND, admin.id, payload.answer)
    if not result.get("success") and result.get("status") != "captcha_required":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "HPC login failed."))
    _after_connect(admin, result)
    return result


def _after_connect(admin: School, result) -> None:
    """Once connected: the activities copy is updated now if it is more than a day old (read-only)."""
    if result.get("status") == "authenticated":
        from backend.services import activity_library
        result["activities_update_started"] = bool(activity_library.maybe_auto_sync(admin.id))


@router.post("/hpc/new-captcha")
def new_school_captcha(admin: School = Depends(require_school_admin)):
    result = hpc_sessions.new_captcha(KIND, admin.id)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "Please click Connect again."))
    return result


@router.post("/hpc/verify-otp")
def verify_school_otp(payload: HpcOtpRequest, admin: School = Depends(require_school_admin)):
    result = hpc_sessions.verify_otp(KIND, admin.id, payload.otp)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "Invalid OTP."))
    _after_connect(admin, result)
    return result


@router.post("/hpc/end-session")
def end_school_session(admin: School = Depends(require_school_admin)):
    audit.record(f"school_admin:{admin.id}", "disconnect_parakh", "settings", admin.id)
    return hpc_sessions.end(KIND, admin.id)


def _roster_file(school_id: str, stage: str):
    return hpc_sessions.session_dir(KIND, school_id) / f"roster_{stage.lower()}.json"


@router.get("/roster")
def get_school_roster(stage: str = "Preparatory", admin: School = Depends(require_school_admin)):
    path = _roster_file(admin.id, stage)
    students = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    synced = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y, %I:%M %p") if path.exists() else None
    return {"success": True, "total_students": len(students), "stage": stage, "last_synced_at": synced, "students": students}


@router.post("/roster/sync")
def sync_school_roster(stage: str = "Preparatory", admin: School = Depends(require_school_admin)):
    client = hpc_sessions.portal_for(KIND, admin.id, admin.hpc_login_id, admin.hpc_password)
    try:
        students = sync.roster_with_details(client, stage, Lookups(client, stage_code(stage)))
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    path = _roster_file(admin.id, stage)
    path.write_text(json.dumps(students, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"success": True, "total_students": len(students), "stage": stage,
            "last_synced_at": datetime.now().strftime("%d %b %Y, %I:%M %p"), "students": students}
