"""
School endpoints: teacher accounts, dashboard stats, the school's HPC session and roster.
"""
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.hpc import sync
from backend.hpc.portal import PortalError, stage_code
from backend.hpc.xl import unpacked_size_ok
from backend.hpc.stages.common import Lookups
from backend.models.entities import School, StudentRecord, Teacher, UploadJob
from backend.schemas.schemas import (
    HpcCaptchaRequest, HpcCredentialsRequest, HpcOtpRequest, HpcSessionStatusResponse, HpcStartSessionRequest,
    TeacherCreateRequest, TeacherResponse, TeacherUpdateRequest,
)
from backend.services import (audit, hpc_sessions, reports_pdf, sdms_aadhaar, sdms_admit, sdms_apaar_excel, sdms_bulk, sdms_data,
                              sdms_sync, udise_parakh, udise_sessions)
from backend.services.safe_paths import inside
from backend.services.auth_service import end_all_sessions, hash_password, require_school_admin

router = APIRouter(prefix="/school", tags=["School"])


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
            "assigned_grade": t.assigned_grade or "",            # never an invented grade or section (L-5)
            "assigned_grades": grades_list,
            "assigned_section": t.assigned_section or "",
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
        grade_str = (payload.assigned_grade or "").strip()

    # Resolve multi-selection for sections
    if payload.assigned_sections and len(payload.assigned_sections) > 0:
        sec_str = ", ".join(dict.fromkeys(sec.strip() for sec in payload.assigned_sections if sec.strip()))
    else:
        sec_str = (payload.assigned_section or "").strip()

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
    if payload.password:                                   # 8+ characters, checked by the schema (H-8)
        teacher.hashed_password = hash_password(payload.password)
        end_all_sessions(db, teacher)                      # the old password's sessions end (M-2)

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
        assigned_grade=teacher.assigned_grade or "",
        assigned_grades=grades_list,
        assigned_section=teacher.assigned_section or "",
        is_active=teacher.is_active,
        last_login=teacher.last_login,
        parakh_connected=p_status.get("logged_in", False),
        parakh_user=p_status.get("user"),
        has_hpc_credentials=bool(teacher.hpc_login_id and teacher.hpc_password_encrypted),
    )


# Teachers from PARAKH: login ID = PARAKH ID; the school sets only this app's password

class ParakhTeacherImport(BaseModel):
    parakh_id: str = Field(..., max_length=30)
    password: Optional[str] = Field(None, max_length=128)


class ParakhTeachersImportRequest(BaseModel):
    teachers: List[ParakhTeacherImport] = Field(..., min_length=1, max_length=200)


@router.get("/teachers/parakh")
def parakh_teacher_list(admin: School = Depends(require_school_admin), db: Session = Depends(get_db)):
    """PARAKH's teachers of the school (school's PARAKH login, read only) and this app's account for each."""
    from backend.services import parakh_teachers
    client = hpc_sessions.portal_for(KIND, admin.id, admin.hpc_login_id, admin.hpc_password)
    try:
        return {"teachers": parakh_teachers.list_teachers(db, admin.id, client)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.post("/teachers/parakh/import")
def parakh_teacher_import(payload: ParakhTeachersImportRequest, admin: School = Depends(require_school_admin),
                          db: Session = Depends(get_db)):
    """Creates / updates teacher accounts from PARAKH (name, teacher code, classes); login ID = PARAKH ID."""
    from backend.services import parakh_teachers, school_register
    client = hpc_sessions.portal_for(KIND, admin.id, admin.hpc_login_id, admin.hpc_password)
    try:
        results = parakh_teachers.import_teachers(db, admin.id, client, [t.model_dump() for t in payload.teachers])
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    school_register.fetch_teacher_classes(admin.id, client)          # who teaches whom, matched to the accounts
    audit.record(f"school_admin:{admin.id}", "teachers_from_parakh", "teacher", admin.id, None,
                 {"results": [{"parakh_id": r["parakh_id"], "status": r["status"]} for r in results]})
    return {"results": results}


@router.delete("/teachers/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teacher(
    teacher_id: str,
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Removes a teacher from use: the account is switched off, not deleted (M-8). Their upload history - the
    record of what was sent to PARAKH - stays; they are signed out everywhere and their saved PARAKH session is
    deleted. The admin can switch the account on again."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id, Teacher.school_id == admin.id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found.")
    teacher.is_active = False
    end_all_sessions(db, teacher)
    hpc_sessions.end("teacher", teacher.id)
    audit.record(f"school_admin:{admin.id}", "deactivate_teacher", "teacher", teacher.id, school_id=admin.id)
    return None


@router.get("/stats")
def get_school_stats(
    admin: School = Depends(require_school_admin),
    db: Session = Depends(get_db)
):
    """Aggregated stats for the school dashboard."""
    teachers = db.query(Teacher).filter(Teacher.school_id == admin.id).all()
    teacher_ids = [t.id for t in teachers]

    total_teachers = len(teachers)
    total_jobs = db.query(UploadJob).filter(UploadJob.teacher_id.in_(teacher_ids)).count() if teacher_ids else 0

    # each student once: an upload (and every retry of it) adds a row per student, so rows are not students
    outcomes: dict = {}
    if teacher_ids:
        for sid, state in (db.query(StudentRecord.admission_number, StudentRecord.status).join(UploadJob)
                           .filter(UploadJob.teacher_id.in_(teacher_ids)).distinct()):
            outcomes.setdefault(sid, set()).add(state)
    on_rosters = set()                                    # the teachers' classes as fetched from PARAKH
    for t in teachers:
        for path in hpc_sessions.session_dir("teacher", t.id).glob("roster_*.json"):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            on_rosters |= {str(x.get("student_id")) for x in (body.get("students") if isinstance(body, dict) else body) or []
                           if isinstance(x, dict) and x.get("student_id")}

    if on_rosters:                                        # uploads of students no longer in a class (old ids) don't count
        outcomes = {sid: states for sid, states in outcomes.items() if sid in on_rosters}
    total_students = len(on_rosters) or len(outcomes)
    success_students = sum(1 for states in outcomes.values() if "SUCCESS" in states)
    failed_students = sum(1 for states in outcomes.values() if "SUCCESS" not in states and states & {"FAILED", "INVALID"})

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


def _stage_name(stage: str) -> str:
    """One of the three stages (any case), or 400 - never part of a path as typed (C-1)."""
    try:
        return stage_code(stage).capitalize()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported stage. Use Foundational, Preparatory or Middle.")


def _roster_file(school_id: str, stage: str):
    return inside(hpc_sessions.session_dir(KIND, school_id), f"roster_{_stage_name(stage).lower()}.json")


@router.get("/roster")
def get_school_roster(stage: str = "Preparatory", admin: School = Depends(require_school_admin)):
    stage = _stage_name(stage)
    path = _roster_file(admin.id, stage)
    students = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    synced = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y, %I:%M %p") if path.exists() else None
    return {"success": True, "total_students": len(students), "stage": stage, "last_synced_at": synced, "students": students}


@router.post("/roster/sync")
def sync_school_roster(stage: str = "Preparatory", admin: School = Depends(require_school_admin)):
    stage = _stage_name(stage)
    client = hpc_sessions.portal_for(KIND, admin.id, admin.hpc_login_id, admin.hpc_password)
    try:
        from backend.services import school_register   # the school's own list: every student of the stage
        rows, _ = school_register.school_list(client, stage)
        students = sync.roster_with_details(client, stage, Lookups(client, stage_code(stage)), records=rows)
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    path = _roster_file(admin.id, stage)
    path.write_text(json.dumps(students, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"success": True, "total_students": len(students), "stage": stage,
            "last_synced_at": datetime.now().strftime("%d %b %Y, %I:%M %p"), "students": students}


# ---------------------------------------------------------------------------
# School Register (docs/school_register_plan.md): every student from PARAKH, and who teaches whom
# ---------------------------------------------------------------------------

class RegisterFetchRequest(BaseModel):
    stages: Optional[List[str]] = Field(None, description="default: every stage")


@router.post("/register/fetch")
def register_fetch(payload: RegisterFetchRequest, admin: School = Depends(require_school_admin)):
    """Starts reading every student of the school from PARAKH (school login; read only, in the background)."""
    from backend.services import school_register
    client = hpc_sessions.portal_for(KIND, admin.id, admin.hpc_login_id, admin.hpc_password)
    stages = [_stage_name(s) for s in payload.stages] if payload.stages else None
    result = school_register.start(admin.id, client, stages)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    return result


@router.get("/register/fetch")
def register_fetch_progress(admin: School = Depends(require_school_admin)):
    from backend.services import school_register
    return school_register.progress(admin.id)


@router.get("/register")
def register_students(stage: Optional[str] = None, admin: School = Depends(require_school_admin)):
    """The school's register: every student (assigned or not), their PARAKH identity and teachers, and what the
    school has entered for them this year (attendance, parents, marks)."""
    from backend.services import register_data, school_register
    out = school_register.students(admin.id, _stage_name(stage) if stage else None)
    try:
        session = register_data.session_of(admin.id)
        entered = register_data.entered(admin.id, session)
    except register_data.Problem:
        session, entered = None, {}
    for row in out["students"]:
        row["entered"] = entered.get(row["id"])
    return {**out, "session": session}


# School settings and the School Data workbook (phase 2)

class RegisterSettingsRequest(BaseModel):
    stage: str
    values: Dict[str, Any]


class RegisterApplyRequest(BaseModel):
    import_id: str = Field(..., max_length=36)
    confirm: bool = False


def _register_problem(exc) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/register/settings")
def register_settings(stage: str, admin: School = Depends(require_school_admin)):
    from backend.services import register_data
    try:
        return register_data.get_settings(admin.id, _stage_name(stage), register_data.session_of(admin.id))
    except register_data.Problem as exc:
        raise _register_problem(exc)


@router.put("/register/settings")
def register_settings_save(payload: RegisterSettingsRequest, admin: School = Depends(require_school_admin)):
    """Working days per month and summative max marks per subject, for a stage (teachers read them)."""
    from backend.services import register_data
    try:
        out = register_data.save_settings(admin.id, _stage_name(payload.stage), register_data.session_of(admin.id),
                                          payload.values, f"school_admin:{admin.id}")
    except register_data.Problem as exc:
        raise _register_problem(exc)
    audit.record(f"school_admin:{admin.id}", "register_settings", "register", admin.id, None,
                 {"stage": out["stage"], "version": out["version"]})
    return out


@router.get("/register/data.xlsx")
def register_data_workbook(admin: School = Depends(require_school_admin)):
    from backend.services import register_data
    try:
        content, name = register_data.workbook(admin.id)
    except register_data.Problem as exc:
        raise _register_problem(exc)
    audit.record(f"school_admin:{admin.id}", "register_download", "register", admin.id, None, {})
    return StreamingResponse(io.BytesIO(content), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/register/data/check")
def register_data_check(file: UploadFile = File(...), admin: School = Depends(require_school_admin)):
    """Checks a filled School Data workbook against the register (nothing is saved yet)."""
    from backend.services import register_data
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 10 MB.")
    try:
        return register_data.check(admin.id, content, file.filename or "School_Data.xlsx", f"school_admin:{admin.id}")
    except register_data.Problem as exc:
        raise _register_problem(exc)


@router.post("/register/data/apply")
def register_data_apply(payload: RegisterApplyRequest, admin: School = Depends(require_school_admin)):
    """Saves the checked workbook's ready rows into the register - only when the person confirmed."""
    from backend.services import register_data
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm first: this saves the rows into the School Register.")
    try:
        return register_data.apply(admin.id, payload.import_id, f"school_admin:{admin.id}")
    except register_data.Problem as exc:
        raise _register_problem(exc)


@router.get("/register/data")
def register_data_status(admin: School = Depends(require_school_admin)):
    from backend.services import register_data
    return {"check": register_data.latest_check(admin.id), "history": register_data.history(admin.id),
            "parents_source": register_data.parents_source(admin.id)}


@router.post("/register/parents/fetch")
def register_parents_fetch(admin: School = Depends(require_school_admin)):
    """Reads UDISE+ (SDMS) again for the parents' names (new admissions included), before a download."""
    from backend.services import register_data
    try:
        out = register_data.fetch_parents(admin.id)
    except register_data.Problem as exc:
        raise _register_problem(exc)
    audit.record(f"school_admin:{admin.id}", "register_parents_fetch", "register", admin.id, None, {"students": out["students"]})
    return out


# ---------------------------------------------------------------------------
# UDISE+: one sign-in, a saved session for each of its four services
# ---------------------------------------------------------------------------

class UdiseConnectRequest(BaseModel):
    username: str = Field("", max_length=20)       # empty: the saved one
    password: str = Field("", max_length=100)


@router.get("/udise/status")
def udise_status(admin: School = Depends(require_school_admin)):
    return udise_sessions.status(admin.id)


@router.post("/udise/connect")
def udise_connect(payload: UdiseConnectRequest, admin: School = Depends(require_school_admin)):
    """Starts the sign-in: UDISE+'s captcha picture comes back for the person to read."""
    return udise_sessions.connect(admin.id, payload.username, payload.password)


@router.post("/udise/new-captcha")
def udise_new_captcha(admin: School = Depends(require_school_admin)):
    return udise_sessions.new_captcha(admin.id)


@router.post("/udise/verify-captcha")
def udise_verify_captcha(payload: HpcCaptchaRequest, admin: School = Depends(require_school_admin)):
    return udise_sessions.verify_captcha(admin.id, payload.answer)


@router.post("/udise/verify-otp")
def udise_verify_otp(payload: HpcOtpRequest, admin: School = Depends(require_school_admin)):
    return udise_sessions.verify_otp(admin.id, payload.otp)


@router.post("/udise/disconnect")
def udise_disconnect(admin: School = Depends(require_school_admin)):
    audit.record(f"school_admin:{admin.id}", "disconnect_udise", "settings", admin.id, None, {})
    return udise_sessions.disconnect(admin.id)


# SDMS: the school's students for the current session (read only)

@router.post("/udise/sdms/fetch")
def sdms_fetch(admin: School = Depends(require_school_admin)):
    """Starts reading every student of every class (in the background)."""
    return sdms_data.start(admin.id)


@router.get("/udise/sdms/fetch")
def sdms_fetch_progress(admin: School = Depends(require_school_admin)):
    return sdms_data.progress(admin.id)


@router.get("/udise/sdms/students")
def sdms_students(admin: School = Depends(require_school_admin)):
    found = sdms_data.view(admin.id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No SDMS data yet. Press 'Fetch all students'.")
    return found


@router.get("/udise/sdms/students.xlsx")
def sdms_students_excel(admin: School = Depends(require_school_admin)):
    content = sdms_data.excel(admin.id)
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No SDMS data yet. Press 'Fetch all students'.")
    audit.record(f"school_admin:{admin.id}", "sdms_download", "udise", admin.id, None, {})
    return StreamingResponse(io.BytesIO(content), headers={"Content-Disposition": 'attachment; filename="SDMS_students.xlsx"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/udise/sdms/completion")
def sdms_completion(admin: School = Depends(require_school_admin)):
    """How many students still have fields SDMS requires, and which fields most often."""
    found = sdms_data.completion_summary(admin.id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No SDMS data yet. Press 'Fetch all students'.")
    return found


@router.get("/udise/sdms/completion.xlsx")
def sdms_completion_excel(admin: School = Depends(require_school_admin)):
    """One sheet: each student (class, section, name, father's name, PEN) and only the fields SDMS requires."""
    content = sdms_data.completion_excel(admin.id)
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No SDMS data yet. Press 'Fetch all students'.")
    audit.record(f"school_admin:{admin.id}", "sdms_download", "udise", admin.id, None, {"sheet": "completion"})
    return StreamingResponse(io.BytesIO(content), headers={"Content-Disposition": 'attachment; filename="SDMS_to_complete.xlsx"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/udise/sdms/new-admissions.xlsx")
def sdms_admission_template(admin: School = Depends(require_school_admin)):
    """A sheet for new admissions: SDMS's Add Student fields, then the rest its form requires (drop-downs in its words)."""
    content = sdms_data.admission_template(admin.id)
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fetch the students once first: the sheet uses the school's classes and SDMS lists.")
    return StreamingResponse(io.BytesIO(content), headers={"Content-Disposition": 'attachment; filename="SDMS_new_admissions.xlsx"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# SDMS updates from the filled completion sheet: upload + validate (nothing sent), then sync (after confirming)

class SdmsSyncRequest(BaseModel):
    confirm: bool = Field(False, description="must be true: the person agreed to save to SDMS")
    only: Optional[List[int]] = Field(None, description="just these students (e.g. one to try first)")


@router.post("/udise/sdms/validate")
def sdms_validate(file: UploadFile = File(...), admin: School = Depends(require_school_admin)):
    """Checks a filled completion sheet against the students SDMS holds: changes and problems. Sends nothing."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 5 MB.")
    if not unpacked_size_ok(content):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not an Excel file the app can read (.xlsx), or it is damaged.")
    result = sdms_sync.validate(admin.id, content, file.filename or "sheet.xlsx")
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


@router.get("/udise/sdms/plan")
def sdms_plan(admin: School = Depends(require_school_admin)):
    return {"plan": sdms_sync.last_plan(admin.id), **sdms_sync.progress(admin.id)}


@router.post("/udise/sdms/sync")
def sdms_sync_start(payload: SdmsSyncRequest, admin: School = Depends(require_school_admin)):
    """Saves the validated changes to SDMS. Only when the request says the person confirmed."""
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm first: this saves the changes to SDMS.")
    result = sdms_sync.start(admin.id, payload.only)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    audit.record(f"school_admin:{admin.id}", "sdms_sync_start", "udise", admin.id, None,
                 {"students": result["students"], "only": payload.only})
    return result


@router.get("/udise/sdms/sync")
def sdms_sync_progress(admin: School = Depends(require_school_admin)):
    return sdms_sync.progress(admin.id)


# SDMS new admissions from the filled New admissions sheet: upload + validate, then add (after confirming)

class SdmsAdmitRequest(BaseModel):
    confirm: bool = Field(False, description="must be true: the person agreed to add these students on SDMS")
    rows: Optional[List[int]] = Field(None, description="just these sheet rows (e.g. one to try first)")


@router.post("/udise/sdms/admit/validate")
def sdms_admit_validate(file: UploadFile = File(...), admin: School = Depends(require_school_admin)):
    """Checks a filled New admissions sheet. Sends nothing."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 5 MB.")
    if not unpacked_size_ok(content):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not an Excel file the app can read (.xlsx), or it is damaged.")
    result = sdms_admit.validate(admin.id, content, file.filename or "sheet.xlsx")
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


@router.get("/udise/sdms/admit")
def sdms_admit_state(admin: School = Depends(require_school_admin)):
    return {"plan": sdms_admit.last_plan(admin.id), **sdms_admit.progress(admin.id)}


@router.post("/udise/sdms/admit")
def sdms_admit_start(payload: SdmsAdmitRequest, admin: School = Depends(require_school_admin)):
    """Adds the checked new students on SDMS. Only when the request says the person confirmed."""
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm first: this adds students on SDMS.")
    result = sdms_admit.start(admin.id, payload.rows)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    audit.record(f"school_admin:{admin.id}", "sdms_admit_start", "udise", admin.id, None,
                 {"students": result["students"], "rows": payload.rows})
    return result


# SDMS: AADHAAR verification and APAAR IDs

class AadhaarVerifyRequest(BaseModel):
    student_ids: List[int] = Field(..., min_length=1, max_length=500)
    consent: bool = Field(False, description="the parents gave consent for demographic authentication of these students")


class AadhaarCorrectRequest(BaseModel):
    aadhaar: str = Field(..., max_length=14, description="the 12 digits exactly as on the AADHAAR card")
    name_as_aadhaar: str = Field(..., max_length=100)
    gender: Optional[int] = Field(None, description="1 Male, 2 Female, 3 Transgender - only to change it")
    dob: Optional[str] = Field(None, description="DD/MM/YYYY - only to change it")
    consent: bool = Field(False, description="the parent gave consent for demographic authentication")


class ApaarRequest(BaseModel):
    relation: int = Field(..., description="1 Father, 2 Mother, 3 Legal Guardian")
    name: str = Field(..., max_length=100)
    id_type: int = Field(..., description="1 AADHAAR, 2 PAN, 3 EPIC/Voter ID, 4 Driving License, 5 Passport")
    id_no: str = Field(..., max_length=30)
    place: str = Field(..., max_length=60)
    date: str = Field(..., description="YYYY-MM-DD: when the parent gave the physical consent")
    consent: bool = Field(False, description="the parent gave this physical consent for the APAAR ID")


@router.get("/udise/sdms/aadhaar")
def sdms_aadhaar_overview(admin: School = Depends(require_school_admin)):
    found = sdms_aadhaar.overview(admin.id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fetch the students from SDMS first.")
    return {**found, **sdms_aadhaar.progress(admin.id)}


@router.post("/udise/sdms/aadhaar/verify")
def sdms_aadhaar_verify(payload: AadhaarVerifyRequest, admin: School = Depends(require_school_admin)):
    """Asks UIDAI again (SDMS's 'AADHAAR Validate'), only with the parents' consent confirmed."""
    if not payload.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm the parents' consent for demographic authentication first.")
    result = sdms_aadhaar.start_verify(admin.id, payload.student_ids)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    return result


@router.post("/udise/sdms/aadhaar/{student_id}/correct")
def sdms_aadhaar_correct(student_id: int, payload: AadhaarCorrectRequest, admin: School = Depends(require_school_admin)):
    """Saves the AADHAAR details exactly as on the card on SDMS, then asks UIDAI again."""
    if not payload.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm the parent's consent for demographic authentication first.")
    result = sdms_aadhaar.correct(admin.id, student_id, payload.aadhaar, payload.name_as_aadhaar, payload.gender, payload.dob)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


@router.post("/udise/sdms/apaar/read")
def sdms_apaar_read(admin: School = Depends(require_school_admin)):
    """Reads SDMS's APAAR status for every class (nothing is changed)."""
    result = sdms_aadhaar.read_apaar(admin.id)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    return result


@router.post("/udise/sdms/apaar/{student_id}")
def sdms_apaar_generate(student_id: int, payload: ApaarRequest, admin: School = Depends(require_school_admin)):
    """Generates one student's APAAR ID with the parent's physical consent."""
    if not payload.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm the parent's physical consent for the APAAR ID first.")
    result = sdms_aadhaar.generate_apaar(admin.id, student_id, payload.model_dump(exclude={"consent"}))
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


# APAAR by Excel: status report, consent sheet, generation from the filled consent sheet

class ApaarSheetRequest(BaseModel):
    confirm: bool = Field(False, description="must be true: the person agreed to generate APAAR IDs on SDMS")
    rows: Optional[List[int]] = Field(None, description="just these sheet rows (e.g. one to try first)")


def _xlsx(content: Optional[bytes], name: str):
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fetch the students and read the APAAR status first.")
    return StreamingResponse(io.BytesIO(content), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/udise/sdms/apaar/status.xlsx")
def sdms_apaar_status_excel(admin: School = Depends(require_school_admin)):
    """Completed (APAAR IDs) and Pending (SDMS's reasons and what to do next)."""
    audit.record(f"school_admin:{admin.id}", "sdms_download", "udise", admin.id, None, {"sheet": "apaar status"})
    return _xlsx(sdms_apaar_excel.status_excel(admin.id), "APAAR_status.xlsx")


@router.get("/udise/sdms/apaar/consent.xlsx")
def sdms_apaar_consent_sheet(admin: School = Depends(require_school_admin)):
    """The students ready for an APAAR ID, with the parent's consent columns to fill."""
    return _xlsx(sdms_apaar_excel.consent_template(admin.id), "APAAR_consent.xlsx")


@router.post("/udise/sdms/apaar/consent/validate")
def sdms_apaar_consent_validate(file: UploadFile = File(...), admin: School = Depends(require_school_admin)):
    """Checks a filled consent sheet. Sends nothing."""
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 5 MB.")
    if not unpacked_size_ok(content):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not an Excel file the app can read (.xlsx), or it is damaged.")
    result = sdms_apaar_excel.validate(admin.id, content, file.filename or "consent.xlsx")
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


@router.get("/udise/sdms/apaar/consent")
def sdms_apaar_consent_state(admin: School = Depends(require_school_admin)):
    return sdms_apaar_excel.state(admin.id)


@router.post("/udise/sdms/apaar/consent/generate")
def sdms_apaar_consent_generate(payload: ApaarSheetRequest, admin: School = Depends(require_school_admin)):
    """Generates APAAR IDs for the checked rows of the consent sheet. Only when the person confirmed."""
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm first: this generates APAAR IDs on SDMS.")
    result = sdms_apaar_excel.start(admin.id, payload.rows)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    audit.record(f"school_admin:{admin.id}", "sdms_apaar_sheet_start", "udise", admin.id, None,
                 {"students": result["students"], "rows": payload.rows})
    return result


# Bulk tools from Excel: class / section shift, Send to Dropbox, Import from the Dropbox, AADHAAR corrections

BULK_FILES = {"shift": "Class_section_shift.xlsx", "dropbox": "Send_to_Dropbox.xlsx", "import": "Import_from_Dropbox.xlsx",
              "aadhaar": "AADHAAR_corrections.xlsx"}


class BulkRunRequest(BaseModel):
    confirm: bool = Field(False, description="must be true: the person agreed to make these changes on SDMS")
    rows: Optional[List[int]] = Field(None, description="just these sheet rows (e.g. one to try first)")


def _bulk_kind(kind: str) -> str:
    if kind not in BULK_FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bulk tool.")
    return kind


@router.get("/udise/sdms/bulk/{kind}/sheet.xlsx")
def sdms_bulk_sheet(kind: str, admin: School = Depends(require_school_admin)):
    """The sheet to fill: this school's students (an empty sheet for an import)."""
    kind = _bulk_kind(kind)
    return _xlsx(sdms_bulk.template(admin.id, kind), BULK_FILES[kind])


@router.post("/udise/sdms/bulk/{kind}/validate")
def sdms_bulk_validate(kind: str, file: UploadFile = File(...), admin: School = Depends(require_school_admin)):
    """Checks a filled sheet. Sends nothing (an import sheet looks each PEN up on SDMS's Dropbox - a read)."""
    kind = _bulk_kind(kind)
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 5 MB.")
    if not unpacked_size_ok(content):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not an Excel file the app can read (.xlsx), or it is damaged.")
    result = sdms_bulk.validate(admin.id, kind, content, file.filename or BULK_FILES[kind])
    if not result.get("ok"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return result


@router.get("/udise/sdms/bulk/{kind}")
def sdms_bulk_state(kind: str, admin: School = Depends(require_school_admin)):
    return sdms_bulk.state(admin.id, _bulk_kind(kind))


@router.post("/udise/sdms/bulk/{kind}/run")
def sdms_bulk_run(kind: str, payload: BulkRunRequest, admin: School = Depends(require_school_admin)):
    """Sends the checked rows to SDMS. Only when the person confirmed; a row done once is never sent again."""
    kind = _bulk_kind(kind)
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirm first: this changes students on SDMS.")
    result = sdms_bulk.start(admin.id, kind, payload.rows)
    if not result.get("started"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    audit.record(f"school_admin:{admin.id}", f"sdms_bulk_{kind}_start", "udise", admin.id, None,
                 {"students": result["students"], "rows": payload.rows})
    return result


# Reports: a printable PDF of each pendency, and UDISE+ against PARAKH

REPORTS = {"aadhaar": "AADHAAR_pending.pdf", "apaar": "APAAR_status.pdf", "completion": "SDMS_forms_pending.pdf",
           "compare": "UDISE_vs_PARAKH.pdf"}


def _school_compare(admin: School, db: Session):
    teacher_ids = [t.id for t in db.query(Teacher).filter(Teacher.school_id == admin.id)]
    return udise_parakh.compare(admin.id, teacher_ids)


@router.get("/udise/compare")
def udise_parakh_compare(admin: School = Depends(require_school_admin), db: Session = Depends(get_db)):
    """Students on UDISE+ and not on PARAKH, and the other way round; matched students whose details differ."""
    result = _school_compare(admin, db)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
    return result


@router.get("/udise/reports/{name}.pdf")
def udise_report_pdf(name: str, admin: School = Depends(require_school_admin), db: Session = Depends(get_db)):
    if name not in REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report.")
    if name == "compare":
        result = _school_compare(admin, db)
        if not result.get("ok"):
            raise HTTPException(status.HTTP_409_CONFLICT, result["error"])
        content = reports_pdf.compare(admin.id, admin, result)
    else:
        content = {"aadhaar": reports_pdf.aadhaar, "apaar": reports_pdf.apaar, "completion": reports_pdf.completion}[name](admin.id, admin)
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fetch the students from SDMS first.")
    audit.record(f"school_admin:{admin.id}", "report_download", "udise", admin.id, None, {"report": name})
    return StreamingResponse(io.BytesIO(content), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{REPORTS[name]}"'})
