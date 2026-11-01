"""
School Register, phase 4: where each student's card stands, for the school - from what actually happened:

  Verified on PARAKH     the last save was read back from PARAKH and matched (upload job SUCCESS / card save
                         COMPLETED), or PARAKH itself lists the card COMPLETED at the school's last fetch
  Submission failed      the last save was refused or did not finish (it can be retried)
  Requires correction    the last save was held back: the card has answers PARAKH would refuse
  Submitted              a save is running now
  Teacher work in progress   the teacher has answers kept in the app, not saved to PARAKH yet
  Assigned to teacher    a teacher has the class, nothing started
  Fetched                on the register, no teacher yet
  No longer on PARAKH    PARAKH stopped listing the student

A click on "upload" alone never makes a student "verified": only a save that was read back, or PARAKH's own status.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.database import SessionLocal
from backend.models.entities import StudentRecord, Teacher, UploadJob
from backend.models.library import AuditLog

ORDER = ["Verified on PARAKH", "Submitted", "Submission failed", "Requires correction", "Teacher work in progress",
         "Assigned to teacher", "Fetched", "No longer on PARAKH"]
RECORD = {"SUCCESS": "Verified on PARAKH", "FAILED": "Submission failed", "INVALID": "Requires correction",
          "PENDING": "Submitted", "IN_PROGRESS": "Submitted"}


def _when(dt: Optional[datetime]) -> str:
    return dt.isoformat(timespec="seconds") + "Z" if dt else ""


def _saves(school_id: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """({PARAKH student id: the latest save - upload job or card}, {teacher id: name})."""
    latest: Dict[str, Dict[str, Any]] = {}

    def keep(sid: str, at: Optional[datetime], status: str, message: str, teacher: str) -> None:
        if not sid or not status:
            return
        old = latest.get(sid)
        if old is None or (at or datetime.min) >= (old["_at"] or datetime.min):
            latest[sid] = {"_at": at, "at": _when(at), "status": status, "message": (message or "")[:300],
                           "teacher": teacher}

    with SessionLocal() as db:
        teachers = {t.id: t.teacher_name for t in db.query(Teacher).filter_by(school_id=school_id)}
        if teachers:
            q = (db.query(StudentRecord.admission_number, StudentRecord.status, StudentRecord.error_message,
                          StudentRecord.completed_at, UploadJob.created_at, UploadJob.teacher_id)
                 .join(UploadJob).filter(UploadJob.teacher_id.in_(list(teachers))))
            for sid, state, error, done, created, tid in q:
                if state in RECORD:
                    keep(str(sid), done or created, RECORD[state], error or "", teachers.get(tid, ""))
        for a in db.query(AuditLog).filter(AuditLog.school_id == school_id, AuditLog.action == "save_to_parakh",
                                           AuditLog.entity == "student"):
            after = a.after or {}
            if after.get("via") != "card":
                continue
            state = "Verified on PARAKH" if after.get("status") == "COMPLETED" else "Submission failed"
            keep(str(a.entity_id), a.at, state, "; ".join(map(str, after.get("errors") or [])),
                 teachers.get((a.actor or "").split(":", 1)[-1], ""))
    return latest, teachers


def _drafts(school_id: str, teachers: Dict[str, str]) -> Dict[Tuple[str, str], str]:
    """{(stage, PARAKH student id): teacher name} for the answers teachers keep in the app (not on PARAKH yet)."""
    from backend.services.hpc_sessions import session_dir
    out = {}
    for tid, name in teachers.items():
        base = session_dir("teacher", tid) / "drafts"
        if not base.exists():
            continue
        for path in base.glob("*/*.json"):
            stage, _, sid = path.stem.partition("_")
            if sid:
                out[(stage.capitalize(), sid)] = name
    return out


def statuses(school_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{register id: {"status", "detail", "at", "teacher"}} for the register's rows (school_register._view)."""
    saves, teachers = _saves(school_id)
    drafts = _drafts(school_id, teachers)
    out = {}
    for r in rows:
        sid = str(r["student_id"])
        save = saves.get(sid)
        if r.get("missing_on_parakh"):
            status, detail, at, who = "No longer on PARAKH", "", "", ""
        elif save and save["status"] in ("Submitted", "Submission failed", "Requires correction"):
            status, detail, at, who = save["status"], save["message"], save["at"], save["teacher"]
        elif save or str(r.get("hpc_status") or "").upper() == "COMPLETED":
            status = "Verified on PARAKH"
            detail = "saved from the app and read back" if save else "PARAKH lists the card complete"
            at, who = (save["at"], save["teacher"]) if save else ("", "")
        elif (r["stage"], sid) in drafts:
            status, detail, at, who = "Teacher work in progress", "answers kept in the app, not saved yet", "", drafts[(r["stage"], sid)]
        elif r.get("teachers"):
            status, detail, at, who = "Assigned to teacher", "", "", ", ".join(r["teachers"])
        else:
            status, detail, at, who = "Fetched", "no teacher has this class", "", ""
        out[r["id"]] = {"status": status, "detail": detail, "at": at, "teacher": who}
    return out


def counts(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """{stage: {status: n}} in ORDER."""
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        s = (r.get("card") or {}).get("status")
        if s:
            out.setdefault(r["stage"], {k: 0 for k in ORDER})[s] += 1
    return out
