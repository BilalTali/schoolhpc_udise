"""
Unified HPC Session Service
Manages isolated HPC PARAKH sessions for both School Admins and Teachers.
Same pattern, same storage structure - just different entity types.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import json
import time
from datetime import datetime
from sqlalchemy.orm import Session
from backend.config import SESSIONS_DIR
from backend.models.entities import (
    School, Teacher,
    SchoolHpcSession, TeacherHpcSession
)


# ---------------------------------------------------------------------------
# Path Helpers
# ---------------------------------------------------------------------------

def get_school_session_dir(school_id: str) -> Path:
    """Isolated directory for a school's HPC session files."""
    d = SESSIONS_DIR / f"school_{school_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_school_storage_path(school_id: str) -> Path:
    return get_school_session_dir(school_id) / "storage_state.json"


def get_teacher_session_dir(teacher_id: str) -> Path:
    """Isolated directory for a teacher's HPC session files."""
    d = SESSIONS_DIR / f"teacher_{teacher_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_teacher_storage_state_path(teacher_id: str) -> Path:
    return get_teacher_session_dir(teacher_id) / "storage_state.json"


# ---------------------------------------------------------------------------
# DB Record Helpers
# ---------------------------------------------------------------------------

def get_or_create_school_session(db: Session, school_id: str) -> SchoolHpcSession:
    record = db.query(SchoolHpcSession).filter(
        SchoolHpcSession.school_id == school_id
    ).first()
    if not record:
        storage_path = str(get_school_storage_path(school_id))
        record = SchoolHpcSession(
            school_id=school_id,
            session_storage_path=storage_path,
            is_active=False
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def get_or_create_teacher_session(db: Session, teacher_id: str) -> TeacherHpcSession:
    record = db.query(TeacherHpcSession).filter(
        TeacherHpcSession.teacher_id == teacher_id
    ).first()
    if not record:
        storage_path = str(get_teacher_storage_state_path(teacher_id))
        record = TeacherHpcSession(
            teacher_id=teacher_id,
            session_storage_path=storage_path,
            is_active=False
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


# Backward-compatible alias used by older code
def get_or_create_session_record(db: Session, teacher_id: str) -> TeacherHpcSession:
    return get_or_create_teacher_session(db, teacher_id)


# ---------------------------------------------------------------------------
# Status Checkers
# ---------------------------------------------------------------------------

def _read_session_status(storage_path: Path) -> Dict[str, Any]:
    """
    Common logic: reads storage_state.json and checks for a valid
    PARAKH session-token cookie + extracts user metadata.
    """
    if not storage_path.exists():
        return {"logged_in": False, "reason": "No session file found"}

    try:
        data = json.loads(storage_path.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        origins = data.get("origins", [])

        user_name = ""
        school_name = ""
        role = "UNKNOWN"
        has_session_token = False

        for c in cookies:
            if "hpc.parakh" in c.get("domain", ""):
                if "session-token" in c.get("name", "").lower():
                    has_session_token = True

        for o in origins:
            if "hpc.parakh.ncert.gov.in" in o.get("origin", ""):
                for item in o.get("localStorage", []):
                    k = item.get("name", "")
                    v = item.get("value", "")
                    if "user" in k.lower() or "profile" in k.lower():
                        try:
                            user_data = json.loads(v)
                            user_name = (
                                user_data.get("name")
                                or user_data.get("username")
                                or ""
                            )
                            school_name = (
                                user_data.get("schoolName")
                                or user_data.get("school_name")
                                or ""
                            )
                            role = user_data.get("role") or role
                        except Exception:
                            pass

        return {
            "logged_in": has_session_token,
            "user": user_name or "HPC User",
            "school": school_name,
            "role": role,
            "storage_path": str(storage_path),
        }
    except Exception as e:
        return {"logged_in": False, "error": str(e)}


def check_school_hpc_status(school_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """Returns the live HPC session status for a school."""
    status = _read_session_status(get_school_storage_path(school_id))
    if db:
        rec = get_or_create_school_session(db, school_id)
        rec.is_active = status["logged_in"]
        if status.get("user"):
            rec.hpc_user_name = status["user"]
        if status.get("school"):
            rec.hpc_school_name = status["school"]
        if status.get("role"):
            rec.hpc_role = status["role"]
        db.commit()
    return status


def check_teacher_hpc_status(teacher_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """Returns the live HPC session status for a teacher."""
    status = _read_session_status(get_teacher_storage_state_path(teacher_id))
    if db:
        rec = get_or_create_teacher_session(db, teacher_id)
        rec.is_active = status["logged_in"]
        if status.get("user"):
            rec.hpc_user_name = status["user"]
        if status.get("school"):
            rec.hpc_school_name = status["school"]
        if status.get("role"):
            rec.hpc_role = status["role"]
        db.commit()
    return status


# Backward-compatible alias
def check_teacher_parakh_status(teacher_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    return check_teacher_hpc_status(teacher_id, db)


# ---------------------------------------------------------------------------
# Session Termination (End Session)
# ---------------------------------------------------------------------------

def end_school_hpc_session(school_id: str, db: Session) -> Dict[str, Any]:
    """Clears the school's HPC session storage and marks it inactive."""
    path = get_school_storage_path(school_id)
    if path.exists():
        path.unlink()
    rec = get_or_create_school_session(db, school_id)
    rec.is_active = False
    rec.hpc_user_name = None
    rec.hpc_school_name = None
    rec.last_authenticated_at = None
    db.commit()
    return {"success": True, "message": "HPC session ended. Storage cleared."}


def end_teacher_hpc_session(teacher_id: str, db: Session) -> Dict[str, Any]:
    """Clears the teacher's HPC session storage and marks it inactive."""
    path = get_teacher_storage_state_path(teacher_id)
    if path.exists():
        path.unlink()
    rec = get_or_create_teacher_session(db, teacher_id)
    rec.is_active = False
    rec.hpc_user_name = None
    rec.hpc_school_name = None
    rec.last_authenticated_at = None
    db.commit()
    return {"success": True, "message": "HPC session ended. Storage cleared."}


# ---------------------------------------------------------------------------
# Session Save Helper (called after successful login)
# ---------------------------------------------------------------------------

def _build_storage_state(access_token: str, user_name: str, school_name: str,
                          role: str, refresh_token: str = "",
                          staff_details: dict = None) -> dict:
    """Builds a Playwright-compatible storage_state dict."""
    return {
        "cookies": [
            {
                "name": "next-auth.session-token",
                "value": access_token or f"hpc_session_{int(time.time())}",
                "domain": "hpc.parakh.ncert.gov.in",
                "path": "/",
                "expires": int(time.time()) + 86400 * 30,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ],
        "origins": [
            {
                "origin": "https://hpc.parakh.ncert.gov.in",
                "localStorage": [
                    {
                        "name": "user",
                        "value": json.dumps({
                            "name": user_name,
                            "school_name": school_name,
                            "role": role,
                            "access_token": access_token,
                            "refresh_token": refresh_token,
                            "staff_details": staff_details or {},
                        }),
                    }
                ],
            }
        ],
    }


def save_school_session(school_id: str, db: Session, access_token: str,
                        user_name: str, school_name: str, role: str = "SCHOOL",
                        refresh_token: str = "", staff_details: dict = None):
    """Persists the school's authenticated HPC session."""
    path = get_school_storage_path(school_id)
    state = _build_storage_state(access_token, user_name, school_name, role,
                                  refresh_token, staff_details)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    rec = get_or_create_school_session(db, school_id)
    rec.is_active = True
    rec.hpc_user_name = user_name
    rec.hpc_school_name = school_name
    rec.hpc_role = role
    rec.last_authenticated_at = datetime.utcnow()
    db.commit()


def save_teacher_session(teacher_id: str, db: Session, access_token: str,
                         user_name: str, school_name: str, role: str = "TEACHER",
                         refresh_token: str = "", staff_details: dict = None):
    """Persists the teacher's authenticated HPC session."""
    path = get_teacher_storage_state_path(teacher_id)
    state = _build_storage_state(access_token, user_name, school_name, role,
                                  refresh_token, staff_details)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    rec = get_or_create_teacher_session(db, teacher_id)
    rec.is_active = True
    rec.hpc_user_name = user_name
    rec.hpc_school_name = school_name
    rec.hpc_role = role
    rec.last_authenticated_at = datetime.utcnow()
    db.commit()
