"""
Backward-Compatible Re-export Module
This file now delegates to hpc_session_service.py.
Older imports from parakh_session_service will continue to work.
"""
from backend.services.hpc_session_service import (
    get_teacher_session_dir,
    get_teacher_storage_state_path,
    get_or_create_teacher_session as get_or_create_session_record,
    check_teacher_hpc_status as check_teacher_parakh_status,
    end_teacher_hpc_session,
    get_school_session_dir,
    get_school_storage_path,
    get_or_create_school_session,
    check_school_hpc_status,
    end_school_hpc_session,
    save_school_session,
    save_teacher_session,
)

# Older function name used by headless_login_service
def launch_teacher_interactive_login(teacher_id: str, db, timeout_seconds: int = 300):
    """Deprecated: Use hpc_auto_login.start_teacher_hpc_session instead."""
    from backend.services.hpc_session_service import get_or_create_teacher_session
    rec = get_or_create_teacher_session(db, teacher_id)
    return {"success": False, "error": "Interactive browser login is no longer used. Use auto-login with saved credentials."}
