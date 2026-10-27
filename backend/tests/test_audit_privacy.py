"""M-7: the audit trail says a UDID or a guardian's name changed, never what it was or became."""
import uuid

from backend.database import SessionLocal
from backend.models.library import AuditLog


def _rows(entity_id):
    with SessionLocal() as db:
        return [(r.before, r.after) for r in db.query(AuditLog).filter(AuditLog.entity_id == entity_id).all()]


def test_new_audit_rows_keep_that_a_sensitive_field_changed_but_not_its_value():
    from backend.services import audit
    sid = f"m7-{uuid.uuid4().hex[:8]}"
    audit.record("teacher:x", "save_draft", "draft", sid, {"a1_udid": "JK0123456789", "a1_guardian_name": "OLD PARENT",
                                                          "a1_mother_tongue": "Urdu"},
                 {"a1_udid": "JK9999999999", "a1_guardian_name": "NEW PARENT", "a1_mother_tongue": "Kashmiri",
                  "stage": "Preparatory"})
    (before, after), = _rows(sid)
    assert before == {"a1_udid": "(changed)", "a1_guardian_name": "(changed)", "a1_mother_tongue": "Urdu"}
    assert after == {"a1_udid": "(changed)", "a1_guardian_name": "(changed)", "a1_mother_tongue": "Kashmiri",
                     "stage": "Preparatory"}


def test_sensitive_values_nested_anywhere_are_hidden_too():
    from backend.services import audit
    sid = f"m7-{uuid.uuid4().hex[:8]}"
    audit.record("teacher:x", "bulk", "draft", sid, None, {"rows": [{"a1_udid": "JK1"}, {"values": {"a1_guardian_name": "P"}}]})
    (_, after), = _rows(sid)
    assert after == {"rows": [{"a1_udid": "(changed)"}, {"values": {"a1_guardian_name": "(changed)"}}]}


def test_existing_rows_are_scrubbed_once_and_the_rest_is_kept():
    from backend.services import audit
    sid = f"m7-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:                            # a row written before this fix
        db.add(AuditLog(actor="teacher:x", entity="draft", entity_id=sid, action="save_draft",
                        before={"a1_udid": "JK0123456789", "a1_present_1": 20},
                        after={"a1_guardian_name": "SOME PARENT", "a1_present_1": 21}))
        db.commit()
    assert audit.scrub_sensitive() >= 1
    (before, after), = _rows(sid)
    assert before == {"a1_udid": "(changed)", "a1_present_1": 20} and after == {"a1_guardian_name": "(changed)", "a1_present_1": 21}
    assert audit.scrub_sensitive() == 0                   # nothing left to scrub
