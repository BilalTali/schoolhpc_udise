"""
Authentication & Authorization Service: Passwords, JWT Tokens & Role Guards
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from backend.database import get_db
from backend.models.entities import School, Teacher

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Dependency to retrieve and authenticate the current logged-in user from Bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header."
        )

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload."
        )

    if role == "SCHOOL_ADMIN":
        school = db.query(School).filter(School.id == user_id, School.is_active == True).first()
        if not school:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School account not found or inactive.")
        return {"user": school, "role": "SCHOOL_ADMIN", "school_id": school.id}

    elif role == "TEACHER":
        teacher = db.query(Teacher).filter(Teacher.id == user_id, Teacher.is_active == True).first()
        if not teacher:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher account not found or inactive.")
        return {"user": teacher, "role": "TEACHER", "school_id": teacher.school_id, "teacher_id": teacher.id}

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unknown user role.")


def require_school_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> School:
    """Guard: Only School Administrators can access this route."""
    if current_user.get("role") != "SCHOOL_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to School Administrators."
        )
    return current_user["user"]


def require_teacher(current_user: Dict[str, Any] = Depends(get_current_user)) -> Teacher:
    """Guard: Only Teachers can access this route."""
    if current_user.get("role") != "TEACHER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to Teachers."
        )
    return current_user["user"]
