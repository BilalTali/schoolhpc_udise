"""Audit trail: drafts and settings are recorded; passwords never are."""
import json

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models.library import AuditLog
from backend.services import hpc_cards, hpc_sessions
from backend.tests.conftest import session_headers  # noqa: E402

API = "/api/v1"


def _teacher(client):
    client.post(f"{API}/auth/school/register", json={
        "udise_code": "33333333333", "school_name": "Audit School", "state": "JK", "district": "Budgam",
        "admin_name": "Admin", "admin_email": "audit@example.com", "password": "secret123"})
    admin_headers, _ = session_headers("33333333333")
    client.post(f"{API}/school/teachers", headers=admin_headers, json={
        "teacher_name": "Audit Teacher", "username": "auditteacher", "password": "secret123", "assigned_stages": ["Preparatory"]})
    headers, login = session_headers("auditteacher")
    return headers, login["user_id"]


def _rows(**filters):
    with SessionLocal() as db:
        return [(r.action, r.before, r.after, r.actor, r.school_id) for r in db.query(AuditLog).filter_by(**filters).all()]


def test_draft_saves_are_audited_with_before_and_after(monkeypatch, tmp_path):
    client = TestClient(app)
    headers, teacher_id = _teacher(client)
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    hpc_cards.save_draft(teacher_id, "2627", "Preparatory", "5001", {"a1_mother_tongue": "Urdu"})
    hpc_cards.save_draft(teacher_id, "2627", "Preparatory", "5001", {"a1_mother_tongue": "Kashmiri"})
    hpc_cards.save_draft(teacher_id, "2627", "Preparatory", "5001", {"a1_mother_tongue": "Kashmiri"})   # no change: no row
    rows = _rows(entity="draft", entity_id="5001", actor=f"teacher:{teacher_id}")
    assert [r[0] for r in rows] == ["save_draft", "save_draft"]
    assert rows[1][1] == {"a1_mother_tongue": "Urdu"} and rows[1][2]["a1_mother_tongue"] == "Kashmiri"
    assert rows[0][4] is not None                                          # school recorded too


def test_saving_parakh_login_never_records_the_password():
    client = TestClient(app)
    headers, teacher_id = _teacher(client)
    res = client.post(f"{API}/teacher/hpc/save-credentials", headers=headers,
                      json={"hpc_login_id": "T123", "hpc_password": "pw-very-secret-9"})
    assert res.status_code == 200
    rows = _rows(action="save_parakh_login", entity_id=teacher_id)
    assert rows and rows[-1][2] == {"hpc_login_id": "T123"}
    with SessionLocal() as db:
        everything = json.dumps([(r.before, r.after) for r in db.query(AuditLog).all()])
    assert "pw-very-secret-9" not in everything
    status = client.get(f"{API}/teacher/hpc/status", headers=headers).json()
    assert "pw-very-secret-9" not in json.dumps(status) and status["has_credentials"] is True
