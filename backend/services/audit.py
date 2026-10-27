"""
Audit trail outside the Activity Library: who changed what, when (drafts, settings, saves to PARAKH).

Rows go to the same audit_log table as the library's. Passwords are never recorded. Writing the
audit row must never stop the work itself, so failures are only printed.
"""
from typing import Any, Optional

from backend.database import SessionLocal
from backend.models.library import AuditLog

# Fields whose values never go into the audit trail - only that they changed (M-7): the UDID (disability) and
# the guardian's name.
SENSITIVE = ("a1_udid", "a1_guardian_name")
HIDDEN = "(changed)"


def _hide(value: Any) -> Any:
    """value with every sensitive field's value replaced by "(changed)", at any depth."""
    if isinstance(value, dict):
        return {k: (HIDDEN if k in SENSITIVE and v != HIDDEN else _hide(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_hide(v) for v in value]
    return value


def record(actor: str, action: str, entity: str, entity_id: Optional[str] = None, before: Any = None,
           after: Any = None, school_id: Optional[str] = None) -> None:
    """actor: "teacher:<id>" or "school_admin:<id>". The school is looked up for teachers when not given.
    Only IDs are stored about people; names are looked up when a history is shown."""
    try:
        with SessionLocal() as db:
            if school_id is None and actor.startswith("teacher:"):
                from backend.models.entities import Teacher
                t = db.get(Teacher, actor.split(":", 1)[1])
                school_id = t.school_id if t else None
            db.add(AuditLog(actor=actor, actor_name=None, school_id=school_id, entity=entity,
                            entity_id=str(entity_id)[:36] if entity_id is not None else None,
                            action=action, before=_hide(before), after=_hide(after)))
            db.commit()
    except Exception as exc:                     # the audit trail must not break saving
        print(f"[audit] could not record {action} on {entity} {entity_id}: {exc}")


def scrub_sensitive() -> int:
    """Hides sensitive values in rows written before M-7. Safe to run again; returns how many rows changed."""
    changed = 0
    with SessionLocal() as db:
        for row in db.query(AuditLog).filter((AuditLog.before.isnot(None)) | (AuditLog.after.isnot(None))).yield_per(500):
            before, after = _hide(row.before), _hide(row.after)
            if before != row.before or after != row.after:
                row.before, row.after = before, after
                changed += 1
        db.commit()
    return changed
