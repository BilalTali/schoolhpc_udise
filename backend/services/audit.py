"""
Audit trail outside the Activity Library: who changed what, when (drafts, settings, saves to PARAKH).

Rows go to the same audit_log table as the library's. Passwords are never recorded. Writing the
audit row must never stop the work itself, so failures are only printed.
"""
from typing import Any, Optional

from backend.database import SessionLocal
from backend.models.library import AuditLog


def record(actor: str, action: str, entity: str, entity_id: Optional[str] = None, before: Any = None,
           after: Any = None, school_id: Optional[str] = None, actor_name: Optional[str] = None) -> None:
    """actor: "teacher:<id>" or "school_admin:<id>". The school is looked up for teachers when not given."""
    try:
        with SessionLocal() as db:
            if school_id is None and actor.startswith("teacher:"):
                from backend.models.entities import Teacher
                t = db.get(Teacher, actor.split(":", 1)[1])
                school_id, actor_name = (t.school_id, actor_name or t.teacher_name) if t else (None, actor_name)
            db.add(AuditLog(actor=actor, actor_name=actor_name, school_id=school_id, entity=entity,
                            entity_id=str(entity_id)[:36] if entity_id is not None else None,
                            action=action, before=before, after=after))
            db.commit()
    except Exception as exc:                     # the audit trail must not break saving
        print(f"[audit] could not record {action} on {entity} {entity_id}: {exc}")
