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

from backend.config import (
    ACCESS_COOKIE_MINUTES, ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_SECURE, JWT_ALGORITHM, JWT_SECRET,
    REFRESH_DAYS_DEFAULT, REFRESH_DAYS_REMEMBER,
)
from backend.database import get_db
from backend.models.entities import RefreshToken, School, Teacher

security = HTTPBearer(auto_error=False)
ACCESS_COOKIE, REFRESH_COOKIE = "ta_access", "ta_refresh"
CSRF_HEADER, CSRF_VALUE = "x-requested-with", "TeacherAssist"
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


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Bearer token returned in the login response (legacy flow)."""
    expire = _now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode({**data, "exp": expire, "iat": _now()}, JWT_SECRET, algorithm=JWT_ALGORITHM)


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


def issue_session(response: Response, db: Session, sub: str, role: str, remember: bool) -> Dict[str, Any]:
    """Sets the access and refresh cookies for a newly signed-in (or refreshed) user."""
    access_exp = _now() + timedelta(minutes=ACCESS_COOKIE_MINUTES)
    access = jwt.encode({"sub": sub, "role": role, "typ": "access", "exp": access_exp, "iat": _now()},
                        JWT_SECRET, algorithm=JWT_ALGORITHM)
    days = REFRESH_DAYS_REMEMBER if remember else REFRESH_DAYS_DEFAULT
    jti = str(uuid.uuid4())
    refresh_exp = _now() + timedelta(days=days)
    refresh = jwt.encode({"sub": sub, "role": role, "typ": "refresh", "jti": jti, "rem": remember,
                          "exp": refresh_exp, "iat": _now()}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    db.add(RefreshToken(id=jti, user_id=sub, role=role, remember=remember,
                        expires_at=refresh_exp.replace(tzinfo=None)))
    db.commit()
    _set_cookie(response, ACCESS_COOKIE, access, ACCESS_COOKIE_MINUTES * 60, "/api")
    _set_cookie(response, REFRESH_COOKIE, refresh, days * 86400, REFRESH_PATH)
    return {"access_expires_in": ACCESS_COOKIE_MINUTES * 60}


def rotate_session(request: Request, response: Response, db: Session) -> Dict[str, Any]:
    """Exchanges a valid refresh cookie for new cookies. Reusing an old one revokes the user's sessions."""
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    row = db.get(RefreshToken, payload.get("jti", ""))
    if payload.get("typ") != "refresh" or row is None:
        clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    if row.revoked_at is not None:
        # A rotated token used again: someone may hold a copy. End every session of this user.
        db.query(RefreshToken).filter(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None)) \
            .update({"revoked_at": _now().replace(tzinfo=None)})
        db.commit()
        clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    _load_user(db, row.user_id, row.role)              # account still exists and is active
    row.revoked_at = _now().replace(tzinfo=None)
    db.commit()
    return issue_session(response, db, row.user_id, row.role, bool(row.remember))


def end_session(request: Request, response: Response, db: Session) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
            row = db.get(RefreshToken, payload.get("jti", ""))
            if row and row.revoked_at is None:
                row.revoked_at = _now().replace(tzinfo=None)
                db.commit()
        except jwt.PyJWTError:
            pass
    clear_session(response)


def clear_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)


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
        return {"user": teacher, "role": role, "school_id": teacher.school_id, "teacher_id": teacher.id}
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown user role.")


def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    if credentials:
        payload = decode_token(credentials.credentials)
    elif request.cookies.get(ACCESS_COOKIE):
        payload = decode_token(request.cookies[ACCESS_COOKIE], expected_type="access")
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing request header.")
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    if not payload.get("sub") or not payload.get("role"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token payload.")
    return _load_user(db, payload["sub"], payload["role"])


def require_school_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> School:
    if current_user.get("role") != "SCHOOL_ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access restricted to School Administrators.")
    return current_user["user"]


def require_teacher(current_user: Dict[str, Any] = Depends(get_current_user)) -> Teacher:
    if current_user.get("role") != "TEACHER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access restricted to Teachers.")
    return current_user["user"]
