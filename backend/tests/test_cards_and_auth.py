"""HPC card endpoints (form, draft, submit, preview, bulk) and the cookie/bearer login flows."""
import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models.entities import Teacher
from backend.routers import hpc_cards as cards_router
from backend.services import hpc_cards, secrets_box
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

API = "/api/v1"
CSRF = {"X-Requested-With": "TeacherAssist"}


def _school_and_teacher(client: TestClient, udise: str, username: str):
    school = {"udise_code": udise, "school_name": "Card School", "state": "JK", "district": "Budgam",
              "admin_name": "Admin", "admin_email": f"{udise}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=school).status_code in (201, 409)   # 409: earlier test made it
    admin = client.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"}).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    client.post(f"{API}/school/teachers", headers=headers, json={
        "teacher_name": "Card Teacher", "username": username, "password": "secret123", "assigned_stages": ["Preparatory"]})
    return headers


@pytest.fixture
def teacher_client(monkeypatch, tmp_path):
    """A logged-in teacher (Bearer) whose portal is a fake with one Preparatory student."""
    client = TestClient(app)
    _school_and_teacher(client, "11111111111", "cardteacher")
    login = client.post(f"{API}/auth/login", json={"identifier": "cardteacher", "password": "secret123"}).json()
    data = blank_student("PREPARATORY")
    portal = FakePortal({("PREPARATORY", "1001"): {"record": data.record, "parts": data.raw_parts}})
    monkeypatch.setattr(cards_router, "_portal", lambda teacher: portal)
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, client, stage: make_lookups("PREPARATORY", portal))
    monkeypatch.setattr(hpc_cards.hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    client.headers["Authorization"] = f"Bearer {login['access_token']}"
    from backend.database import SessionLocal
    from backend.models.library import LibraryActivity
    with SessionLocal() as db:                 # no library yet: activities come from PARAKH's own lists
        db.query(LibraryActivity).delete()
        db.commit()
    return client, portal


# ---------------------------------------------------------------------------
# HPC card endpoints
# ---------------------------------------------------------------------------

def test_sessions_and_fields(teacher_client):
    client, _ = teacher_client
    assert client.get(f"{API}/teacher/sessions").json()["sessions"] == [
        {"code": "2627", "label": "2026-27", "terms": [], "current": True, "read_only": False}]
    parts = client.get(f"{API}/teacher/hpc-cards/Preparatory/fields").json()["parts"]
    assert [p["code"] for p in parts] == ["A1", "A2", "A3", "B", "C", "D"]
    medium = next(f for f in parts[0]["fields"] if f["key"] == "a1_medium")
    assert medium["kind"] == "choice" and "English" in medium["options"] and medium["required"]


def test_card_draft_and_submit_flow(teacher_client):
    client, portal = teacher_client
    card = client.get(f"{API}/teacher/hpc-cards/Preparatory/1001").json()
    assert card["student"]["student_name"] == "TEST STUDENT" and card["ready"] is False and card["draft"] is None
    assert any("Mother Tongue" in p for p in card["parts"][0]["problems"])

    # Autosave the whole card in two edits; the second must name the version it started from.
    row = filled_row("PREPARATORY")
    row["a1_interests"] = ["Reading", "Art"]                       # lists for multi-choice fields
    first = {k: v for k, v in row.items() if k.startswith("a")}
    rest = {k: v for k, v in row.items() if not k.startswith("a")}
    v1 = client.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft", json={"values": first}).json()
    stale = client.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft", json={"values": rest, "base_version": 0})
    assert stale.status_code == 409                                  # another tab saved in between
    v2 = client.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft",
                    json={"values": rest, "base_version": v1["version"]}).json()
    assert v2["version"] == 2 and v2["problems"] == {}

    card = client.get(f"{API}/teacher/hpc-cards/Preparatory/1001").json()
    assert card["ready"] is True and card["draft"]["version"] == 2
    a1 = {f["key"]: f for f in card["parts"][0]["fields"]}
    assert a1["a1_interests"]["value"] == ["Reading", "Art"] and a1["a1_interests"]["changed"]

    preview = client.get(f"{API}/teacher/hpc-cards/Preparatory/1001/preview").json()
    a1_items = {i["label"]: i["value"] for i in preview["sections"][0]["items"]}
    assert a1_items["Mother Tongue"] == "Kashmiri" and preview["includes_draft"] is True

    result = client.post(f"{API}/teacher/hpc-cards/Preparatory/1001/submit", headers=CSRF).json()
    assert result["status"] == "COMPLETED", result
    assert [p["hpc_col"] for _, _, p in portal.saved] == ["part_a1", "part_a2", "part_a3", "part_b", "part_c", "hpc_credit"]
    assert client.get(f"{API}/teacher/hpc-cards/Preparatory/1001").json()["draft"] is None   # draft cleared


def test_invalid_values_and_unknown_fields(teacher_client):
    client, portal = teacher_client
    bad = client.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft",
                     json={"values": {"a1_medium": "Klingon", "a1_mother_tongue": "x" * 30}}).json()
    assert "is not one of" in bad["problems"]["a1_medium"] and "allows 20" in bad["problems"]["a1_mother_tongue"]
    unknown = client.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft", json={"values": {"nope": 1}})
    assert unknown.status_code == 422
    # An incomplete card is not written to the portal.
    result = client.post(f"{API}/teacher/hpc-cards/Preparatory/1001/submit").json()
    assert result["status"] == "INVALID" and portal.saved == []


def test_bulk_entry(teacher_client):
    client, _ = teacher_client
    read = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a1_mother_tongue"}).json()
    assert read["field"]["part"] == "A1" and read["rows"][0]["student_id"] == "1001" and read["rows"][0]["value"] == ""
    write = client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk",
                       json={"field": "a1_mother_tongue", "values": {"1001": "Urdu", "9999": "x" * 40}}).json()
    assert write["saved"] == ["1001"] and "allows 20" in write["problems"]["9999"]
    again = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a1_mother_tongue"}).json()
    assert again["rows"][0]["value"] == "Urdu" and again["rows"][0]["in_draft"] is True
    assert client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "zzz"}).status_code == 404
    # Bulk entry is only for class-wide answers; names, relations and Part B are not offered.
    for key in ("a1_guardian_relation", "a1_guardian_name", "a2_name", "b_self_1", "d_declaration", "a1_medium"):
        assert client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": key}).status_code == 404, key
    assert client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk",
                      json={"field": "a2_name", "values": {"1001": "x"}}).status_code == 404
    common = client.get(f"{API}/teacher/hpc-cards/Preparatory/fields", params={"common": True}).json()["parts"]
    assert [p["code"] for p in common] == ["A1", "A3", "C"]
    keys = {f["key"] for p in common for f in p["fields"]}
    assert {"a1_mother_tongue", "a3_feel_1", "a3_peer2_6", "a3_parent_11", "a3_resources", "a3_support",
            "c_PSLS1_awareness", "c_PSLS7_creativity"} <= keys
    assert not keys & {"a1_guardian_relation", "a1_interests", "a3_peer1_name", "a3_resources_other", "c_PSLS1_remark"}
    assert len(keys) == 1 + 7 + 12 + 1 + 11 + 1 + 21
    level = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "c_PSLS3_awareness"}).json()
    assert level["field"]["part"] == "C" and level["field"]["options"] == ["Beginner", "Proficient", "Advanced"]


def test_unknown_session_and_stage(teacher_client):
    client, _ = teacher_client
    assert client.get(f"{API}/teacher/hpc-cards/Preparatory/1001", params={"session": "2425"}).status_code == 404
    assert client.get(f"{API}/teacher/hpc-cards/Secondary/1001").status_code == 400


# ---------------------------------------------------------------------------
# Login: cookies, refresh rotation, logout, CSRF guard, bearer still works
# ---------------------------------------------------------------------------

def test_cookie_session_lifecycle():
    client = TestClient(app)
    _school_and_teacher(client, "22222222222", "cookieteacher")
    client.cookies.clear()
    login = client.post(f"{API}/auth/login", json={"identifier": "cookieteacher", "password": "secret123", "remember_me": True})
    assert login.status_code == 200 and "ta_access" in login.cookies and "ta_refresh" in login.cookies
    assert "httponly" in login.headers["set-cookie"].lower()

    me = client.get(f"{API}/auth/me")                                  # cookie only, no Authorization header
    assert me.status_code == 200 and me.json()["role"] == "TEACHER" and me.json()["assigned_stages"] == ["Preparatory"]
    assert client.post(f"{API}/teacher/hpc/end-session").status_code == 403            # no CSRF header
    assert client.post(f"{API}/teacher/hpc/end-session", headers=CSRF).status_code == 200

    old_refresh = client.cookies.get("ta_refresh")
    assert client.post(f"{API}/auth/refresh").status_code == 200      # rotates
    assert client.cookies.get("ta_refresh") != old_refresh
    new_refresh = client.cookies.get("ta_refresh")

    # Re-using the rotated token ends every session of that user.
    thief = TestClient(app)
    thief.cookies.set("ta_refresh", old_refresh, path="/api/v1/auth")
    assert thief.post(f"{API}/auth/refresh").status_code == 401
    client.cookies.set("ta_refresh", new_refresh, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401

    # Fresh login, then logout revokes it.
    client.post(f"{API}/auth/login", json={"identifier": "cookieteacher", "password": "secret123"})
    assert client.post(f"{API}/auth/logout").status_code == 200
    assert client.post(f"{API}/auth/refresh").status_code == 401
    assert client.get(f"{API}/auth/me").status_code == 401


def test_bearer_flow_still_works_and_refresh_token_is_not_an_access_token():
    client = TestClient(app)
    _school_and_teacher(client, "33333333333", "bearerteacher")
    client.cookies.clear()
    login = client.post(f"{API}/auth/login", json={"identifier": "bearerteacher", "password": "secret123"})
    token = login.json()["access_token"]
    refresh = login.cookies["ta_refresh"]
    client.cookies.clear()
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_passwords_are_encrypted_and_never_sent():
    client = TestClient(app)
    admin_headers = _school_and_teacher(client, "44444444444", "secretteacher")
    teachers = client.get(f"{API}/school/teachers", headers=admin_headers).json()
    assert teachers and all("plain_password" not in t for t in teachers)
    login = client.post(f"{API}/auth/login", json={"identifier": "secretteacher", "password": "secret123"}).json()
    t_headers = {"Authorization": f"Bearer {login['access_token']}"}
    client.post(f"{API}/teacher/hpc/save-credentials", headers=t_headers,
                json={"hpc_login_id": "T123", "hpc_password": "portal-pass"})
    status = client.get(f"{API}/teacher/hpc/status", headers=t_headers).json()
    assert status["has_credentials"] is True and "saved_hpc_password" not in status
    with SessionLocal() as db:
        t = db.query(Teacher).filter(Teacher.username == "secretteacher").one()
        assert secrets_box.is_encrypted(t.hpc_password_encrypted) and t.hpc_password == "portal-pass"
        assert t.plain_password is None



def test_part_c_levels_for_the_whole_class(teacher_client):
    client, _ = teacher_client
    read = client.get(f"{API}/teacher/hpc-cards/Preparatory/levels").json()
    assert read["options"] == ["Beginner", "Proficient", "Advanced"]
    assert [s["code"] for s in read["subjects"]] == [f"PSLS{i}" for i in range(1, 8)]
    assert read["subjects"][2] == {"code": "PSLS3", "name": "Mathematics", "fields": [
        {"key": "c_PSLS3_awareness", "ability": "Awareness"}, {"key": "c_PSLS3_sensitivity", "ability": "Sensitivity"},
        {"key": "c_PSLS3_creativity", "ability": "Creativity"}]}
    assert read["rows"][0]["student_id"] == "1001" and len(read["rows"][0]["values"]) == 21
    write = client.put(f"{API}/teacher/hpc-cards/Preparatory/levels", json={"values": {
        "1001": {"c_PSLS3_awareness": "Advanced"}, "1002": {"c_PSLS3_remark": "x"}, "1003": {"c_PSLS1_awareness": "Great"}}}).json()
    assert write["saved"] == ["1001"] and set(write["problems"]) == {"1002", "1003"}
    again = client.get(f"{API}/teacher/hpc-cards/Preparatory/levels").json()
    assert again["rows"][0]["values"]["c_PSLS3_awareness"] == "Advanced" and again["rows"][0]["in_draft"] == ["c_PSLS3_awareness"]
