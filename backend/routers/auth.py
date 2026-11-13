"""
Authentication Router: School Registration (One School = One UDISE) & Login
"""
import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.entities import PlatformAdmin, School, Teacher
from backend.schemas.schemas import (
    SchoolRegisterRequest, SchoolResponse, LoginRequest, TokenResponse
)
from backend.config import SCHOOL_APPROVAL
from backend.services import login_limits
from backend.services.auth_service import (
    bearer_enabled, create_access_token, end_session, get_current_user, hash_password, issue_session, rotate_session,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/school/register", response_model=SchoolResponse, status_code=status.HTTP_201_CREATED)
def register_school(payload: SchoolRegisterRequest, db: Session = Depends(get_db)):
    """
    Registers a new School.
    STRICT RULE: One School = One Registration.
    UDISE code must be unique across the entire system.
    """
    # 1. Enforce strict UDISE code uniqueness
    existing_udise = db.query(School).filter(School.udise_code == payload.udise_code).first()
    if existing_udise:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This UDISE code is already registered. Each school can register only once - ask your school's "
                   "admin to sign in, or contact support."      # never another school's name (L-2)
        )

    # 2. Enforce admin email uniqueness
    existing_email = db.query(School).filter(School.admin_email == payload.admin_email.strip().lower()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this admin email already exists."
        )

    # 3. Create School entity with hashed password
    new_school = School(
        udise_code=payload.udise_code,
        school_name=payload.school_name.strip(),
        state=payload.state.strip(),
        district=payload.district.strip(),
        block=payload.block.strip() if payload.block else None,
        admin_name=payload.admin_name.strip(),
        admin_email=payload.admin_email.strip().lower(),
        admin_phone=payload.admin_phone.strip() if payload.admin_phone else None,
        hashed_password=hash_password(payload.password),
        is_active=not SCHOOL_APPROVAL,                  # waits for the app admin's approval
        approval="PENDING" if SCHOOL_APPROVAL else "APPROVED",
    )
    db.add(new_school)
    db.commit()
    db.refresh(new_school)
    return new_school


def _address(request: Request) -> str:
    """The browser's network address. Behind the web app's own dev server (on this computer) it is the one
    that server passes on in X-Forwarded-For."""
    host = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and host in ("127.0.0.1", "::1", "localhost"):
        return forwarded.split(",")[0].strip()
    return host


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Unified Login endpoint.
    Supports:
      1. School: using 11-digit UDISE code or Admin Email
      2. Teacher: using Username
    Repeated wrong passwords make the next attempt wait, longer each time (H-8).
    """
    identifier = payload.identifier.strip()
    clean_id_lower = identifier.lower()
    address = _address(request)
    wait = login_limits.check(identifier, address)
    if wait:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)},
                            detail=f"Too many wrong passwords. Please try again in {wait} second{'s' if wait != 1 else ''}.")

    # The admin: its login ID comes from .env; the password is set once, on this PC
    from backend import config
    if config.APP_ADMIN_LOGIN and clean_id_lower == config.APP_ADMIN_LOGIN:
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.login == config.APP_ADMIN_LOGIN).first()
        if admin is None and config.APP_ADMIN_PASSWORD:          # the password kept in .env: the account follows it
            admin = PlatformAdmin(login=config.APP_ADMIN_LOGIN, hashed_password=hash_password(config.APP_ADMIN_PASSWORD))
            db.add(admin)
            db.commit()
        if admin is None:
            raise HTTPException(status.HTTP_409_CONFLICT, {"setup_required": True, "message":
                                "Set the admin's password first (only from a browser on the server PC)."})
        good = (hmac.compare_digest(payload.password.encode("utf-8"), config.APP_ADMIN_PASSWORD.encode("utf-8"))
                if config.APP_ADMIN_PASSWORD else verify_password(payload.password, admin.hashed_password))
        if good and admin.is_active:
            login_limits.succeeded(identifier)
            admin.last_login = datetime.utcnow()
            db.commit()
            issue_session(response, db, admin.id, "APP_ADMIN", payload.remember_me)
            return TokenResponse(access_token="", role="APP_ADMIN", user_id=admin.id, name="Admin")
        login_limits.failed(identifier, address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials. Please verify your UDISE/Username and Password.")

    # Case 1: Try School match (by UDISE or Email)
    school = db.query(School).filter(
        (School.udise_code == identifier) | (School.admin_email == clean_id_lower)
    ).first()

    if school and verify_password(payload.password, school.hashed_password):
        if school.approval == "PENDING":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your school's registration is waiting for approval by the "
                                "app admin. You can sign in as soon as it is approved.")
        if school.approval == "REJECTED":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your school's registration was not approved. Contact the "
                                "app admin.")
        if not school.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="School account is disabled.")
        login_limits.succeeded(identifier)
        issue_session(response, db, school.id, "SCHOOL_ADMIN", payload.remember_me)
        token = create_access_token({
            "sub": school.id,
            "role": "SCHOOL_ADMIN",
            "name": school.admin_name,
            "udise": school.udise_code,
            "school_id": school.id,
            "school_name": school.school_name
        }, epoch=school.token_epoch or 0) if bearer_enabled() else ""
        return TokenResponse(
            access_token=token,
            role="SCHOOL_ADMIN",
            user_id=school.id,
            name=school.admin_name,
            school_id=school.id,
            school_name=school.school_name,
            udise_code=school.udise_code,
        )

    # Case 2: Try Teacher match (by username): exactly as typed, else ignoring case (older accounts were saved in
    # lowercase; a teacher may type their ID in capitals)
    teacher = db.query(Teacher).filter(Teacher.username == identifier).first() or \
        db.query(Teacher).filter(func.lower(Teacher.username) == clean_id_lower).first()

    if teacher and verify_password(payload.password, teacher.hashed_password):
        if not teacher.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher account is disabled.")
        login_limits.succeeded(identifier)

        teacher.last_login = datetime.utcnow()
        db.commit()
        issue_session(response, db, teacher.id, "TEACHER", payload.remember_me)
        school_obj = teacher.school
        token = create_access_token({
            "sub": teacher.id,
            "role": "TEACHER",
            "name": teacher.teacher_name,
            "username": teacher.username,
            "school_id": teacher.school_id,
            "school_name": school_obj.school_name if school_obj else "School"
        }, epoch=teacher.token_epoch or 0) if bearer_enabled() else ""
        stages_list = [s.strip() for s in (teacher.assigned_stage or "").split(",") if s.strip()]
        grades_list = [g.strip() for g in (teacher.assigned_grade or "").split(",") if g.strip()]
        return TokenResponse(
            access_token=token,
            role="TEACHER",
            user_id=teacher.id,
            name=teacher.teacher_name,
            school_id=teacher.school_id,
            school_name=school_obj.school_name if school_obj else None,
            assigned_stage=teacher.assigned_stage,
            assigned_stages=stages_list if stages_list else ["Preparatory"],
            assigned_grade=teacher.assigned_grade,
            assigned_grades=grades_list,
            assigned_section=teacher.assigned_section
        )

    login_limits.failed(identifier, address)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials. Please verify your UDISE/Username and Password."
    )


class AppAdminSetup(BaseModel):
    login: str
    password: str = Field(..., min_length=12, description="At least 12 characters")


@router.post("/app-admin/setup")
def setup_app_admin(payload: AppAdminSetup, request: Request, db: Session = Depends(get_db)):
    """Sets the admin's password the first time. Only for the login ID in .env, only once, and only
    from a browser on the server PC itself (so nobody who merely learns the login ID can claim the account)."""
    from backend import config
    from backend.services import audit
    if not config.APP_ADMIN_LOGIN or payload.login.strip().lower() != config.APP_ADMIN_LOGIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That is not the admin's login ID.")
    if _address(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Set this password from a browser on the server PC itself.")
    if db.query(PlatformAdmin).filter(PlatformAdmin.login == config.APP_ADMIN_LOGIN).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "The admin's password is already set.")
    admin = PlatformAdmin(login=config.APP_ADMIN_LOGIN, hashed_password=hash_password(payload.password))
    db.add(admin)
    db.commit()
    audit.record(f"app_admin:{admin.id}", "setup_app_admin", "platform_admin", admin.id)
    return {"success": True, "message": "Password set. Sign in with the login ID and this password."}


@router.get("/me")
def get_my_profile(current=Depends(get_current_user)):
    """Inspects active authenticated session and claims."""
    u = current["user"]
    role = current["role"]
    if role == "APP_ADMIN":
        return {"role": role, "id": u.id, "name": "Admin", "login": u.login}
    if role == "SCHOOL_ADMIN":
        return {
            "role": role,
            "id": u.id,
            "name": u.admin_name,
            "email": u.admin_email,
            "udise_code": u.udise_code,
            "school_name": u.school_name,
            "state": u.state,
            "district": u.district
        }
    else:
        return {
            "role": role,
            "id": u.id,
            "name": u.teacher_name,
            "username": u.username,
            "assigned_stages": u.stages,
            "assigned_grades": [g.strip() for g in (u.assigned_grade or "").split(",") if g.strip()],
            "assigned_stage": u.assigned_stage,
            "assigned_grade": u.assigned_grade,
            "assigned_section": u.assigned_section,
            "school_id": u.school_id,
            "school_name": u.school.school_name if u.school else ""
        }


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Renews the cookie session (call shortly before the 15-minute access cookie runs out, or after a 401)."""
    return {"success": True, **rotate_session(request, response, db)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Ends this browser's cookie session. Other tabs of the web app are told by the app itself."""
    end_session(request, response, db)
    return {"success": True}
