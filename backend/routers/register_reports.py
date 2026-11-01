"""School Register reports (phase 6). School: the school report, the UDISE+ / APAAR / PARAKH comparison (counts for the
dashboard and Excel). Teacher: their own students only. Built from what the app holds; nothing is read from the
portals here."""
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.models.entities import School, Teacher
from backend.services import audit, register_data, register_reports
from backend.services.auth_service import require_school_admin, require_teacher

school_router = APIRouter(prefix="/school/register/reports", tags=["School Register reports"])
teacher_router = APIRouter(prefix="/teacher/register", tags=["School Register reports"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(content: bytes, name: str) -> StreamingResponse:
    return StreamingResponse(io.BytesIO(content), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@school_router.get("/school.xlsx")
def school_report(admin: School = Depends(require_school_admin)):
    content, name = register_reports.school_report(admin.id)
    audit.record(f"school_admin:{admin.id}", "register_report", "register", admin.id, None, {"report": "school"})
    return _file(content, name)


@school_router.get("/reconciliation")
def reconciliation(admin: School = Depends(require_school_admin)):
    """UDISE+ / APAAR / PARAKH counts for the school's dashboard."""
    return register_reports.reconciliation(admin.id)


@school_router.get("/reconciliation.xlsx")
def reconciliation_report(admin: School = Depends(require_school_admin)):
    try:
        content, name = register_reports.reconciliation_report(admin.id)
    except register_data.Problem as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    audit.record(f"school_admin:{admin.id}", "register_report", "register", admin.id, None, {"report": "reconciliation"})
    return _file(content, name)


@teacher_router.get("/report.xlsx")
def teacher_report(teacher: Teacher = Depends(require_teacher)):
    content, name = register_reports.teacher_report(teacher)
    return _file(content, name)
