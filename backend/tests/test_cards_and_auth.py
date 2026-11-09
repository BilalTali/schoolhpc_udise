"""HPC card endpoints (form, draft, submit, preview, bulk) and the cookie/bearer login flows."""
import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models.entities import Teacher
from backend.routers import hpc_cards as cards_router
from backend.services import hpc_cards, secrets_box
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups, session_headers

API = "/api/v1"
CSRF = {"X-Requested-With": "TeacherAssist"}


def _school_and_teacher(client: TestClient, udise: str, username: str):
    school = {"udise_code": udise, "school_name": "Card School", "state": "JK", "district": "Budgam",
              "admin_name": "Admin", "admin_email": f"{udise}@example.com", "password": "secret123"}
    assert client.post(f"{API}/auth/school/register", json=school).status_code in (201, 409)   # 409: earlier test made it
    headers, _ = session_headers(udise)
    client.post(f"{API}/school/teachers", headers=headers, json={
        "teacher_name": "Card Teacher", "username": username, "password": "secret123", "assigned_stages": ["Preparatory"]})
    return headers


@pytest.fixture
def teacher_client(monkeypatch, tmp_path):
    """A signed-in teacher (cookie session) whose portal is a fake with one Preparatory student."""
    client = TestClient(app)
    _school_and_teacher(client, "11111111111", "cardteacher")
    data = blank_student("PREPARATORY")
    portal = FakePortal({("PREPARATORY", "1001"): {"record": data.record, "parts": data.raw_parts}})
    monkeypatch.setattr(cards_router, "_portal", lambda teacher: portal)
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, client, stage: make_lookups("PREPARATORY", portal))
    monkeypatch.setattr(hpc_cards.hpc_sessions, "session_dir", lambda kind, i: tmp_path)
    client.headers.update(session_headers("cardteacher")[0])
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
    assert any("Guardian Name" in p for p in card["parts"][0]["problems"])

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
    too_long = client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk",
                          json={"field": "a1_mother_tongue", "values": {"1001": "x" * 40}}).json()
    assert too_long["saved"] == [] and "allows 20" in too_long["problems"]["1001"]
    write = client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk",
                       json={"field": "a1_mother_tongue", "values": {"1001": "Urdu", "9999": "Urdu"}}).json()
    assert write["saved"] == ["1001"] and "not in your class list" in write["problems"]["9999"]   # C-2
    again = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a1_mother_tongue"}).json()
    assert again["rows"][0]["value"] == "Urdu" and again["rows"][0]["in_draft"] is True
    assert client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "zzz"}).status_code == 404
    # Bulk entry is only for class-wide answers; names, relations and class settings are not offered.
    for key in ("a1_guardian_relation", "a1_guardian_name", "a3_peer1_name", "d_declaration", "a1_medium"):
        assert client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": key}).status_code == 404, key
    assert client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk",
                      json={"field": "a1_guardian_name", "values": {"1001": "x"}}).status_code == 404
    common = client.get(f"{API}/teacher/hpc-cards/Preparatory/fields", params={"common": True}).json()["parts"]
    assert [p["code"] for p in common] == ["A1", "A2", "A3", "B", "C"]
    keys = {f["key"] for p in common for f in p["fields"]}
    meta = {f["key"]: f for p in common for f in p["fields"]}
    assert {"a1_mother_tongue", "a3_feel_1", "a3_peer2_6", "a3_parent_11", "a3_resources", "a3_support",
            "c_PSLS1_awareness", "c_PSLS7_creativity"} <= keys
    # text answers with ready phrases are class-wide too: favourites, goals, each subject's remark ...
    assert {"a2_fav_food", "a2_fav_festival", "a2_grow_up", "a2_idol", "c_PSLS1_remark", "c_PSLS7_remark"} <= keys
    assert all(len(x) <= meta["a2_idol"]["max_len"] for x in meta["a2_idol"]["suggestions"])
    # never: what differs per student (names, age, friends, relations), "other" boxes, marks
    assert not keys & {"a1_guardian_relation", "a1_guardian_name", "a1_interests", "a3_peer1_name",
                       "a3_resources_other", "d_1_obtained"}
    # name and age are class-wide too: "Mix all" fills them from the class list and the date of birth
    assert meta["a2_name"]["from_records"] == "name" and meta["a2_age"]["from_records"] == "age"
    # Preparatory's hand (A7): each finger its own prompt and short phrases; facts about the child, never mixed
    assert meta["a2_about_1"]["label"] == "Things about me: I am good at"
    assert "Drawing" in meta["a2_about_1"]["suggestions"] and "My parents" not in meta["a2_about_1"]["suggestions"]
    assert meta["a2_about_1"]["mixable"] is False
    # mother tongue: suggestions to pick from, but never handed out at random
    assert "Kashmiri" in meta["a1_mother_tongue"]["suggestions"] and meta["a1_mother_tongue"]["mixable"] is False
    # Part C notes: no stock phrases (C1) - "Mix all" writes each from the student's own levels for the subject
    assert meta["c_PSLS1_remark"]["from_records"] == "levels" and meta["c_PSLS1_remark"]["suggestions"] == []
    part_b = {f["key"] for p in common if p["code"] == "B" for f in p["fields"]}
    assert {"b_self_1", "b_self_8", "b_observation", "b_challenges"} <= part_b         # every Part B answer, text too
    # the Part C levels grid holds only the levels; the remarks are bulk entry's
    levels = client.get(f"{API}/teacher/hpc-cards/Preparatory/levels").json()
    assert all(not f["key"].endswith("_remark") for subj in levels["subjects"] for f in subj["fields"])
    level = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "c_PSLS3_awareness"}).json()
    assert level["field"]["part"] == "C" and level["field"]["options"] == ["Beginner", "Proficient", "Advanced"]

    # Part B's self-assessment for the whole class (the Activities tab and the Excel file do not hold it);
    # the class check and the upload take it from the draft, like the grid's choices
    sa = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "b_self_5"}).json()
    assert sa["field"]["part"] == "B" and sa["field"]["required"] is True and sa["field"]["options"]
    answer = sa["field"]["options"][0]
    done = client.put(f"{API}/teacher/hpc-cards/Preparatory/bulk", json={"field": "b_self_5", "values": {"1001": answer}}).json()
    assert done["saved"] == ["1001"]
    again = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "b_self_5"}).json()
    assert again["rows"][0]["value"] == answer and again["rows"][0]["in_draft"] is True
    # how many students have each Part B answer: the screen marks a question done or says how many are left
    progress = client.get(f"{API}/teacher/hpc-cards/Preparatory/progress", params={"part": "B"}).json()
    assert progress["total"] >= 1 and progress["fields"]["b_self_5"] == {"filled": 1, "required": True}
    assert client.get(f"{API}/teacher/hpc-cards/Preparatory/progress", params={"part": "Z"}).status_code == 404


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


def test_bearer_flow_still_works_and_refresh_token_is_not_an_access_token(monkeypatch):
    from datetime import date
    from backend import config
    monkeypatch.setattr(config, "BEARER_LAST_DAY", date(2999, 1, 1))    # the old login, while it still exists (M-2)
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
    t_headers, _ = session_headers("secretteacher")
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


def test_bulk_entry_loads_from_the_apps_stored_copy(teacher_client, monkeypatch, tmp_path):
    client, portal = teacher_client
    reads = []
    real = portal.student

    def counted(stage, student_id, hpc_col=None):
        reads.append((student_id, hpc_col))
        return real(stage, student_id, hpc_col)
    monkeypatch.setattr(portal, "student", counted)

    first = client.get(f"{API}/teacher/hpc-cards/Preparatory/levels").json()
    assert reads == [("1001", "part_c")] and first["read_at"]
    reads.clear()
    client.get(f"{API}/teacher/hpc-cards/Preparatory/levels")                       # again: from the stored copy
    client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "c_PSLS1_awareness"})
    assert reads == []
    client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a1_mother_tongue"})
    assert reads == [("1001", "part_a1")]                                            # a part not kept yet
    reads.clear()
    client.get(f"{API}/teacher/hpc-cards/Preparatory/levels", params={"refresh": True})   # "Read again from PARAKH"
    assert reads == [("1001", "part_c")]

    # after a save, only that student's copy is dropped (the next view reads it fresh)
    from backend.services import activity_grid, card_store
    reads.clear()
    activity_grid.forget(client.get(f"{API}/auth/me").json()["id"], "Preparatory", "1001")
    client.get(f"{API}/teacher/hpc-cards/Preparatory/levels")
    assert reads == [("1001", "part_c")]
    assert card_store.CARDS_DIR.exists() and str(card_store.CARDS_DIR).startswith(str(tmp_path.parent))


def test_bulk_entry_uses_the_class_list_fetched_on_the_roster_tab(teacher_client, monkeypatch, tmp_path):
    client, portal = teacher_client
    import json
    (tmp_path / "roster_preparatory.json").write_text(json.dumps([
        {"student_id": "1001", "student_name": "FROM THE STORED LIST", "grade": "Grade 5", "section": "A", "status": "PENDING"}]),
        encoding="utf-8")
    monkeypatch.setattr(portal, "roster", lambda stage: (_ for _ in ()).throw(AssertionError("PARAKH asked for the class")))
    rows = client.get(f"{API}/teacher/hpc-cards/Preparatory/levels").json()["rows"]
    assert [r["student_name"] for r in rows] == ["FROM THE STORED LIST"]


def test_submitting_a_card_reads_it_from_parakh_only_once(teacher_client, monkeypatch):
    client, portal = teacher_client
    reads = []
    real = portal.student

    def counted(stage, student_id, hpc_col=None):
        reads.append(hpc_col)
        return real(stage, student_id, hpc_col)
    monkeypatch.setattr(portal, "student", counted)
    status = client.post(f"{API}/teacher/hpc-cards/Preparatory/1001/submit").json()["status"]
    checks_after = 1 if status == "COMPLETED" else 0                                 # the record read after saving
    assert reads.count(None) == 1 + checks_after and len(reads) == 7 + checks_after  # record + 6 parts, read once


def test_students_this_login_cannot_open_are_counted_by_class():
    # PARAKH lists Grade 1 students to a login that is class teacher of Balvatika 3; it refuses their cards (403)
    from types import SimpleNamespace
    from backend.hpc import sync
    from backend.hpc.portal import Portal
    p = object.__new__(Portal)
    p.session = SimpleNamespace(staff={"grade_section_mapping": [{"grd": 3, "sec": 1}]})
    p.not_yours = {}
    p.roster_page = lambda stage, page_no, page_size=100: {"records": [
        {"id": 1, "grade_id": 4, "section_id": 1}, {"id": 2, "grade_id": 4, "section_id": 1},
        {"id": 3, "grade_id": 3, "section_id": 1}]}
    assert [r["id"] for r in p.roster("Foundational")] == [3]
    lookups = SimpleNamespace(grades=[{"id": 4, "grade_caption": "Grade 1"}], section_name=lambda sid: "A")
    assert sync.not_yours(p, "Foundational", lookups) == [{"grade": "Grade 1", "section": "A", "count": 2}]


def test_mix_every_question_at_once(teacher_client):
    """One click: every question on the screen gets mixed answers (only empty ones unless replace), one save."""
    client, _ = teacher_client
    url = f"{API}/teacher/hpc-cards/Preparatory/bulk-mix"
    fields = ["a3_feel_1", "a3_feel_2", "a2_fav_festival", "a1_mother_tongue", "a3_resources", "b_self_1"]
    preview = client.post(url, json={"fields": fields}).json()
    assert preview["applied"] is False and preview["students"] >= 1
    assert {f["key"] for f in preview["fields"]} == {"a3_feel_1", "a3_feel_2", "a2_fav_festival", "b_self_1"}
    reasons = {s["key"]: s["reason"] for s in preview["skipped"]}
    assert "fact about each student" in reasons["a1_mother_tongue"] and "several options" in reasons["a3_resources"]
    before = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a3_feel_1"}).json()
    assert before["rows"][0]["in_draft"] is False                              # the preview saved nothing

    done = client.post(url, json={"fields": fields, "apply": True}).json()
    assert done["applied"] is True and done["cells"] == preview["cells"]
    row = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a3_feel_1"}).json()
    assert row["rows"][0]["in_draft"] is True and row["rows"][0]["value"] in row["field"]["options"]
    festival = client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": "a2_fav_festival"}).json()
    assert festival["rows"][0]["value"] in festival["field"]["suggestions"]
    # everything is filled now: only-empty fills nothing more; replace fills them all again
    assert client.post(url, json={"fields": fields}).json()["cells"] == 0
    assert client.post(url, json={"fields": fields, "replace": True}).json()["cells"] == done["cells"]


def test_mix_all_fills_name_and_age_from_records_and_never_the_hand(teacher_client):
    client, _ = teacher_client
    url = f"{API}/teacher/hpc-cards/Preparatory/bulk-mix"
    hand = [f"a2_about_{i}" for i in range(1, 6)]
    done = client.post(url, json={"fields": ["a2_name", "a2_age", *hand], "apply": True}).json()
    assert {f["key"] for f in done["fields"] if f["filled"]} == {"a2_name", "a2_age"}
    assert {s["key"] for s in done["skipped"]} == set(hand)                  # A7: facts about the child, not mixed
    rows = {k: client.get(f"{API}/teacher/hpc-cards/Preparatory/bulk", params={"field": k}).json()["rows"][0]
            for k in ["a2_name", "a2_age"]}
    assert rows["a2_name"]["value"] == "Test Student"                       # the class list's name
    assert rows["a2_age"]["value"].isdigit() and 5 <= int(rows["a2_age"]["value"]) <= 20      # from the date of birth

