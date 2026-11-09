"""
App login: password hashing, tokens and role guards.

Two ways to authenticate a request (both accepted while the web app migrates):
  cookie  ta_access (httpOnly, 15 min) + ta_refresh (httpOnly, rotating, 1 or 30 days).
          Unsafe methods (POST/PUT/PATCH/DELETE) must also send the header
          X-Requested-With: TeacherAssist, which a cross-site form cannot add (CSRF guard).
  bearer  Authorization: Bearer <access_token> from the login response (legacy, 7 days).
Refresh tokens are recorded server-side so logout and reuse of a rotated token revoke them.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend import config
from backend.config import (
    ACCESS_COOKIE_MINUTES, ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_SECURE, JWT_ALGORITHM, JWT_SECRET,
    REFRESH_DAYS_DEFAULT, REFRESH_DAYS_REMEMBER,
)
from backend.database import get_db
from backend.models.entities import PlatformAdmin, RefreshToken, School, Teacher

security = HTTPBearer(auto_error=False)
ACCESS_COOKIE, REFRESH_COOKIE = "ta_access", "ta_refresh"
CSRF_HEADER, CSRF_VALUE = "x-requested-with", "TeacherAssist"
# A teacher tab the school opened ("Open as teacher"): its own cookies, used only by a tab that sends
# "X-TA-Tab: teacher:<id>". The school's own session in the first tab is never touched.
TAB_HEADER = "x-ta-tab"
TAB_ACCESS_COOKIE, TAB_REFRESH_COOKIE = "ta_access_t", "ta_refresh_t"


def tab_teacher(request: Request) -> Optional[str]:
    """The teacher id a teacher tab says it is ("teacher:<id>"), or None for an ordinary tab."""
    value = (request.headers.get(TAB_HEADER) or "").strip()
    return value[len("teacher:"):] or None if value.startswith("teacher:") else None


def _cookie_names(tab: bool):
    return (TAB_ACCESS_COOKIE, TAB_REFRESH_COOKIE) if tab else (ACCESS_COOKIE, REFRESH_COOKIE)
REFRESH_PATH = "/api/v1/auth"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def bearer_enabled() -> bool:
    """The legacy Bearer login works until config.BEARER_LAST_DAY (M-2)."""
    return _now().date() <= config.BEARER_LAST_DAY


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None, epoch: int = 0) -> str:
    """Bearer token returned in the login response (legacy flow): 24 hours, ended by logout or a password change."""
    expire = _now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode({**data, "ep": epoch, "exp": expire, "iat": _now()}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def end_all_sessions(db: Session, user) -> None:
    """After a password change: every token of this account stops working - Bearer, cookie and refresh (M-2)."""
    user.token_epoch = (user.token_epoch or 0) + 1
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)) \
        .update({"revoked_at": _now().replace(tzinfo=None)})
    db.commit()


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    if expected_type and payload.get("typ") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    if payload.get("typ") == "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    return payload


# ---------------------------------------------------------------------------
# Cookie sessions
# ---------------------------------------------------------------------------

def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=COOKIE_SECURE, samesite="lax", path=path)


def issue_session(response: Response, db: Session, sub: str, role: str, remember: bool,
                  tab: bool = False) -> Dict[str, Any]:
    """Sets the access and refresh cookies for a newly signed-in (or refreshed) user; tab: the teacher-tab cookies."""
    access_name, refresh_name = _cookie_names(tab)
    access_exp = _now() + timedelta(minutes=ACCESS_COOKIE_MINUTES)
    epoch = _load_user(db, sub, role)["user"].token_epoch or 0
    access = jwt.encode({"sub": sub, "role": role, "typ": "access", "ep": epoch, "exp": access_exp, "iat": _now()},
                        JWT_SECRET, algorithm=JWT_ALGORITHM)
    days = REFRESH_DAYS_REMEMBER if remember else REFRESH_DAYS_DEFAULT
    jti = str(uuid.uuid4())
    refresh_exp = _now() + timedelta(days=days)
    refresh = jwt.encode({"sub": sub, "role": role, "typ": "refresh", "jti": jti, "rem": remember,
                          "exp": refresh_exp, "iat": _now()}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    db.add(RefreshToken(id=jti, user_id=sub, role=role, remember=remember,
                        expires_at=refresh_exp.replace(tzinfo=None)))
    db.commit()
    _set_cookie(response, access_name, access, ACCESS_COOKIE_MINUTES * 60, "/api")
    _set_cookie(response, refresh_name, refresh, days * 86400, REFRESH_PATH)
    return {"access_expires_in": ACCESS_COOKIE_MINUTES * 60}


def rotate_session(request: Request, response: Response, db: Session) -> Dict[str, Any]:
    """Exchanges a valid refresh cookie for new cookies. Reusing an old one revokes the user's sessions.
    A teacher tab renews its own cookies, and only for the teacher it was opened for."""
    tab_id = tab_teacher(request)
    tab = tab_id is not None
    token = request.cookies.get(_cookie_names(tab)[1])
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        clear_session(response, tab)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    row = db.get(RefreshToken, payload.get("jti", ""))
    if payload.get("typ") != "refresh" or row is None:
        clear_session(response, tab)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    if row.revoked_at is not None:
        # A rotated token used again: someone may hold a copy. End every session of this user.
        db.query(RefreshToken).filter(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None)) \
            .update({"revoked_at": _now().replace(tzinfo=None)})
        db.commit()
        clear_session(response, tab)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    if tab and (row.user_id != tab_id or row.role != "TEACHER"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This tab was opened for another teacher. Close it and press "
                                                          "'Open as teacher' again on the school's page.")
    _load_user(db, row.user_id, row.role)              # account still exists and is active
    row.revoked_at = _now().replace(tzinfo=None)
    db.commit()
    return issue_session(response, db, row.user_id, row.role, bool(row.remember), tab=tab)


def end_session(request: Request, response: Response, db: Session) -> None:
    tab = tab_teacher(request) is not None              # a teacher tab signs out only itself
    bearer = request.headers.get("authorization", "")
    if not tab and bearer.lower().startswith("bearer "):          # the old login: logging out ends its tokens (M-2)
        try:
            payload = decode_token(bearer[7:].strip())
            user = _load_user(db, payload.get("sub", ""), payload.get("role", ""))["user"]
            user.token_epoch = (user.token_epoch or 0) + 1
            db.commit()
        except HTTPException:
            pass
    token = request.cookies.get(_cookie_names(tab)[1])
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
            row = db.get(RefreshToken, payload.get("jti", ""))
            if row and row.revoked_at is None:
                row.revoked_at = _now().replace(tzinfo=None)
                db.commit()
        except jwt.PyJWTError:
            pass
    clear_session(response, tab)


def clear_session(response: Response, tab: bool = False) -> None:
    access_name, refresh_name = _cookie_names(tab)
    response.delete_cookie(access_name, path="/api")
    response.delete_cookie(refresh_name, path=REFRESH_PATH)


# ---------------------------------------------------------------------------
# Who is calling
# ---------------------------------------------------------------------------

def _load_user(db: Session, user_id: str, role: str) -> Dict[str, Any]:
    if role == "SCHOOL_ADMIN":
        school = db.query(School).filter(School.id == user_id, School.is_active == True).first()  # noqa: E712
        if not school:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "School account not found or inactive.")
        return {"user": school, "role": role, "school_id": school.id}
    if role == "TEACHER":
        teacher = db.query(Teacher).filter(Teacher.id == user_id, Teacher.is_active == True).first()  # noqa: E712
        if not teacher:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Teacher account not found or inactive.")
        if teacher.school is not None and not teacher.school.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your school's account is switched off.")
        return {"user": teacher, "role": role, "school_id": teacher.school_id, "teacher_id": teacher.id}
    if role == "APP_ADMIN":
        admin = db.query(PlatformAdmin).filter(PlatformAdmin.id == user_id, PlatformAdmin.is_active == True).first()  # noqa: E712
        if not admin:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin account not found.")
        return {"user": admin, "role": role, "school_id": None}
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown user role.")


def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    tab_id = tab_teacher(request)
    if tab_id is not None:                              # a teacher tab: only its own cookie, only its teacher
        token = request.cookies.get(TAB_ACCESS_COOKIE)
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This teacher tab has ended. Open it again from the "
                                                              "school's page ('Open as teacher').")
        payload = decode_token(token, expected_type="access")
        if payload.get("sub") != tab_id or payload.get("role") != "TEACHER":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This tab was opened for another teacher. Close it and "
                                                              "press 'Open as teacher' again on the school's page.")
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing request header.")
    elif credentials:
        if not bearer_enabled():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This way of signing in has ended. Please sign in again.")
        payload = decode_token(credentials.credentials)
    elif request.cookies.get(ACCESS_COOKIE):
        payload = decode_token(request.cookies[ACCESS_COOKIE], expected_type="access")
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing request header.")
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    if not payload.get("sub") or not payload.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token payload.")
    current = _load_user(db, payload["sub"], payload["role"])
    if payload.get("ep", 0) != (current["user"].token_epoch or 0):   # logged out, or the password changed (M-2)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Please sign in again.")
    return current


def require_school_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> School:
    if current_user.get("role") != "SCHOOL_ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access restricted to the school account.")
    return current_user["user"]


def require_app_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> PlatformAdmin:
    if current_user.get("role") != "APP_ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access restricted to the admin.")
    return current_user["user"]


def require_teacher(current_user: Dict[str, Any] = Depends(get_current_user)) -> Teacher:
    if current_user.get("role") != "TEACHER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access restricted to Teachers.")
    return current_user["user"]
