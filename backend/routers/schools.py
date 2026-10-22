"""
Schools Router: School Admin Dashboard, Teacher Management & HPC Session Control
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.entities import School, Teacher, SchoolHpcSession, UploadJob, StudentRecord
from backend.schemas.schemas import (
    TeacherCreateRequest, TeacherResponse,
    HpcCredentialsRequest, HpcStartSessionRequest, HpcOtpRequest, HpcSessionStatusResponse
)
from backend.services.auth_service import require_school_admin, hash_password
from backend.services.hpc_session_service import (
    check_school_hpc_status, check_teacher_hpc_status,
    end_school_hpc_session
)
from backend.services.hpc_auto_login import (
    start_school_hpc_session, verify_hpc_otp
)

router = APIRouter(prefix="/school", tags=["School Administration"])


# ---------------------------------------------------------------------------
# Teacher CRUD
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
        p_status = check_teacher_hpc_status(t.id, db=db)
        t_dict = {
            "id": t.id,
            "school_id": t.school_id,
            "teacher_name": t.teacher_name,
            "employee_code": t.employee_code,
            "username": t.username,
            "mobile_number": t.mobile_number,
            "assigned_stage": t.assigned_stage,
            "assigned_grade": t.assigned_grade,
            "assigned_section": t.assigned_section,
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
    Assigns: unique username, stage (Preparatory/Middle), class, and section.
    """
    existing = db.query(Teacher).filter(Teacher.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken. Please choose another username."
        )

    new_teacher = Teacher(
        school_id=admin.id,
        teacher_name=payload.teacher_name.strip(),
        employee_code=payload.employee_code.strip() if payload.employee_code else None,
        username=payload.username.strip().lower(),
        mobile_number=payload.mobile_number.strip() if payload.mobile_number else None,
        hashed_password=hash_password(payload.password),
        assigned_stage=payload.assigned_stage,
        assigned_grade=payload.assigned_grade,
        assigned_section=payload.assigned_section,
        is_active=True
    )
    db.add(new_teacher)
    db.commit()
    db.refresh(new_teacher)

    return TeacherResponse(
        id=new_teacher.id,
        school_id=new_teacher.school_id,
        teacher_name=new_teacher.teacher_name,
        employee_code=new_teacher.employee_code,
        username=new_teacher.username,
        mobile_number=new_teacher.mobile_number,
        assigned_stage=new_teacher.assigned_stage,
        assigned_grade=new_teacher.assigned_grade,
        assigned_section=new_teacher.assigned_section,
        is_active=new_teacher.is_active,
        last_login=None,
        parakh_connected=False,
        has_hpc_credentials=False,
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
    failed_students = sum(1 for s in student_records if s.status == "FAILED")

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
# School HPC Session Endpoints
# ---------------------------------------------------------------------------

@router.get("/hpc/status", response_model=HpcSessionStatusResponse)
def get_school_hpc_status(
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Returns the current HPC PARAKH session status for this school admin."""
    result = check_school_hpc_status(admin.id, db=db)
    return HpcSessionStatusResponse(
        logged_in=result.get("logged_in", False),
        user=result.get("user"),
        school=result.get("school"),
        role=result.get("role"),
        reason=result.get("reason") or result.get("error"),
    )


@router.post("/hpc/save-credentials")
def save_school_hpc_credentials(
    payload: HpcCredentialsRequest,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Saves (or updates) the school admin's HPC login credentials."""
    admin.hpc_login_id = payload.hpc_login_id.strip()
    admin.hpc_password_encrypted = payload.hpc_password  # Store as-is; encrypt later with Fernet if needed
    db.commit()
    return {"success": True, "message": "HPC credentials saved. Click 'Start Session' to connect."}


@router.post("/hpc/start-session")
def start_school_session(
    payload: HpcStartSessionRequest,
    background_tasks: BackgroundTasks,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """
    Auto-starts the HPC PARAKH session for the school admin.
    Uses saved credentials (or override from payload).
    Auto-solves captcha and logs in.
    """
    login_id = payload.hpc_login_id or admin.hpc_login_id
    password = payload.hpc_password or admin.hpc_password_encrypted

    if not login_id or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HPC credentials not found. Please save your HPC Login ID and password first."
        )

    result = start_school_hpc_session(admin.id, login_id, password, db)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "HPC session start failed.")
        )
    return result


@router.post("/hpc/verify-otp")
def verify_school_otp(
    payload: HpcOtpRequest,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Verifies OTP for school HPC login."""
    result = verify_hpc_otp(f"school_{admin.id}", payload.otp, db)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Invalid OTP.")
        )
    return result


@router.post("/hpc/end-session")
def end_school_session(
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Ends (clears) the school's active HPC session."""
    result = end_school_hpc_session(admin.id, db)
    return result
