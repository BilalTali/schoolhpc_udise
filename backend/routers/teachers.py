"""
Teacher Router: HPC Session Control, Roster Sync & Batch Upload
"""
from pathlib import Path
import shutil
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.database import get_db, SessionLocal
from backend.models.entities import Teacher, UploadJob, StudentRecord
from backend.schemas.schemas import (
    ValidationReportResponse, UploadJobResponse,
    HpcCredentialsRequest, HpcStartSessionRequest, HpcOtpRequest, HpcSessionStatusResponse
)
from backend.services.auth_service import require_teacher
from backend.services.hpc_session_service import (
    check_teacher_hpc_status, end_teacher_hpc_session,
    get_teacher_session_dir, get_teacher_storage_state_path
)
from backend.services.hpc_auto_login import (
    start_teacher_hpc_session, verify_hpc_otp
)
from backend.config import DATA_DIR, AUTOMATION_ROOT

# Import existing core automation engines
import sys
if str(AUTOMATION_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_ROOT))

from excel.importer import import_preparatory_workbook
from excel.validator import validate_workbook_records
from excel.template_generator import build_preparatory_template
from portal.student_fetcher import fetch_students_from_portal, generate_prepopulated_excel

router = APIRouter(prefix="/teacher", tags=["Teacher Workflows"])


# ---------------------------------------------------------------------------
# HPC Session Endpoints
# ---------------------------------------------------------------------------

@router.get("/hpc/status", response_model=HpcSessionStatusResponse)
def get_teacher_hpc_status(
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Returns current HPC session status for the authenticated teacher."""
    result = check_teacher_hpc_status(teacher.id, db=db)
    return HpcSessionStatusResponse(
        logged_in=result.get("logged_in", False),
        user=result.get("user"),
        school=result.get("school"),
        role=result.get("role"),
        reason=result.get("reason") or result.get("error"),
    )


@router.post("/hpc/save-credentials")
def save_teacher_hpc_credentials(
    payload: HpcCredentialsRequest,
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Saves (or updates) the teacher's own HPC login credentials."""
    teacher.hpc_login_id = payload.hpc_login_id.strip()
    teacher.hpc_password_encrypted = payload.hpc_password
    db.commit()
    return {"success": True, "message": "HPC credentials saved. Click 'Start Session' to connect."}


@router.post("/hpc/start-session")
def start_teacher_session(
    payload: HpcStartSessionRequest,
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """
    Auto-starts the HPC PARAKH session for the teacher.
    Uses saved credentials (or override from payload).
    Auto-solves arithmetic captcha and logs in.
    """
    login_id = payload.hpc_login_id or teacher.hpc_login_id
    password = payload.hpc_password or teacher.hpc_password_encrypted

    if not login_id or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HPC credentials not found. Please save your HPC Login ID and password first."
        )

    result = start_teacher_hpc_session(teacher.id, login_id, password, db)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "HPC session start failed.")
        )
    return result


@router.post("/hpc/verify-otp")
def verify_teacher_otp(
    payload: HpcOtpRequest,
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Verifies OTP for teacher HPC login."""
    result = verify_hpc_otp(f"teacher_{teacher.id}", payload.otp, db)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Invalid OTP.")
        )
    return result


@router.post("/hpc/end-session")
def end_teacher_session(
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Ends (clears) the teacher's active HPC session."""
    result = end_teacher_hpc_session(teacher.id, db)
    return result


# ---------------------------------------------------------------------------
# Legacy PARAKH Status (backward compat)
# ---------------------------------------------------------------------------

@router.get("/parakh/status")
def get_parakh_status(
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Legacy: Checks if the authenticated teacher has a valid, active PARAKH session."""
    return check_teacher_hpc_status(teacher.id, db=db)


# ---------------------------------------------------------------------------
# Roster Sync & Download
# ---------------------------------------------------------------------------

@router.post("/roster/sync")
def sync_roster(
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Fetches students from PARAKH using this teacher's isolated session."""
    p_status = check_teacher_hpc_status(teacher.id, db=db)
    if not p_status.get("logged_in"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Teacher is not authenticated on the PARAKH portal. Start your HPC session first."
        )

    teacher_dir = get_teacher_session_dir(teacher.id)
    profile_dir = teacher_dir / "browser_profile"
    out_excel = teacher_dir / f"roster_{teacher.assigned_stage.lower()}_{teacher.id}.xlsx"

    try:
        students = fetch_students_from_portal(stage=teacher.assigned_stage, headless=True, profile_dir=profile_dir)
        if not students:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No students found for stage '{teacher.assigned_stage}'. Verify assigned classes on PARAKH."
            )
        generate_prepopulated_excel(students, stage=teacher.assigned_stage, output_file=out_excel)
        return {
            "success": True,
            "total_students": len(students),
            "stage": teacher.assigned_stage,
            "excel_ready": True
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/roster/download")
def download_prefilled_excel(
    teacher: Teacher = Depends(require_teacher)
):
    """Downloads the pre-populated Excel workbook for offline grading."""
    teacher_dir = get_teacher_session_dir(teacher.id)
    out_excel = teacher_dir / f"roster_{teacher.assigned_stage.lower()}_{teacher.id}.xlsx"

    if not out_excel.exists():
        clean_tmpl = teacher_dir / f"HPC_{teacher.assigned_stage}_Template.xlsx"
        build_preparatory_template(output_path=clean_tmpl)
        out_excel = clean_tmpl

    return FileResponse(
        path=out_excel,
        filename=f"HPC_{teacher.assigned_stage}_{teacher.assigned_grade}_{teacher.assigned_section}_Grading.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------------------------------------------------------------------
# Upload & Validate
# ---------------------------------------------------------------------------

@router.post("/upload/validate", response_model=ValidationReportResponse)
async def validate_excel(
    file: UploadFile = File(...),
    teacher: Teacher = Depends(require_teacher)
):
    """Uploads and pre-flight validates Excel file against PARAKH DOM limits and grades."""
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported.")

    teacher_dir = get_teacher_session_dir(teacher.id)
    upload_path = teacher_dir / f"uploaded_{file.filename}"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        records = import_preparatory_workbook(upload_path)
        if not records:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workbook contains no student records.")

        detected_stage = teacher.assigned_stage
        first_grade = str(records[0].get("data", {}).get("grade", "")).lower()
        if any(g in first_grade for g in ("6", "7", "8", "middle")):
            detected_stage = "Middle"
        elif any(g in first_grade for g in ("3", "4", "5", "prep")):
            detected_stage = "Preparatory"

        report = validate_workbook_records(records)
        sample_data = records[0].get("data", {})

        return ValidationReportResponse(
            is_valid=report.is_valid,
            total_records=len(records),
            detected_stage=detected_stage,
            error_count=len(report.errors),
            warning_count=len(report.warnings),
            errors=[{"row": e.row, "field": e.field, "message": e.message} for e in report.errors],
            warnings=[{"row": w.row, "field": w.field, "message": w.message} for w in report.warnings],
            seeder_working_days=sample_data.get("working_days", "271"),
            seeder_max_marks=sample_data.get("max_summative_marks", "33")
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse workbook: {e}")


def _execute_background_upload(job_id: str, teacher_id: str, file_path: str, stage: str):
    """Background task executing Playwright automation."""
    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if not job:
            return
        job.status = "IN_PROGRESS"
        db.commit()

        records = import_preparatory_workbook(file_path)
        teacher_dir = get_teacher_session_dir(teacher_id)
        profile_dir = teacher_dir / "browser_profile"
        from portal.uploader import upload_batch_students
        results = upload_batch_students(records, headless=True, stage=stage, profile_dir=profile_dir)

        job.status = "COMPLETED" if results["failed"] == 0 else "PARTIAL_SUCCESS"
        job.success_count = results["success"]
        job.failed_count = results["failed"]
        db.commit()
    except Exception:
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            db.commit()
    finally:
        db.close()


@router.post("/upload/submit", response_model=UploadJobResponse)
def submit_upload_job(
    file_name: str,
    background_tasks: BackgroundTasks,
    teacher: Teacher = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    """Enqueues automated submission of a validated Excel file in the background."""
    teacher_dir = get_teacher_session_dir(teacher.id)
    upload_path = teacher_dir / f"uploaded_{file_name}"

    if not upload_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded file not found. Validate first.")

    records = import_preparatory_workbook(upload_path)
    detected_stage = teacher.assigned_stage
    if records:
        first_grade = str(records[0].get("data", {}).get("grade", "")).lower()
        if any(g in first_grade for g in ("6", "7", "8", "middle")):
            detected_stage = "Middle"
        elif any(g in first_grade for g in ("3", "4", "5", "prep")):
            detected_stage = "Preparatory"

    new_job = UploadJob(
        teacher_id=teacher.id,
        original_filename=file_name,
        detected_stage=detected_stage,
        status="PENDING",
        total_students=len(records)
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    background_tasks.add_task(
        _execute_background_upload,
        str(new_job.id),
        teacher.id,
        str(upload_path),
        detected_stage
    )

    return UploadJobResponse(
        job_id=new_job.id,
        status=new_job.status,
        total_students=new_job.total_students,
        success_count=new_job.success_count,
        failed_count=new_job.failed_count,
        detected_stage=new_job.detected_stage,
        created_at=new_job.created_at
    )
