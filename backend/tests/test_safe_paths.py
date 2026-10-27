"""Findings C-1 and C-2: values from a request never make a file path leave the account's folder.

The sweep sends traversal values (.., ../, ..\\, absolute paths, URL-encoded forms, a NUL byte) to every
route that takes an id, a stage or a file name, as a teacher and as a school admin, then checks that
files planted outside the account's folders were neither read, changed nor deleted, and that nothing
new was written outside them."""
import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.services import safe_paths
from backend.tests.conftest import FakePortal, blank_student, make_lookups

API = "/api/v1"
SECRET = "CANARY-SECRET-NOT-FOR-THIS-ACCOUNT"
HDR = {"X-Requested-With": "TeacherAssist"}


# ---------------------------------------------------------------------------
# The helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", ".", "..", "../x", "..\\x", "a/b", "a\\b", "C:\\x", "C:x", "/etc/passwd",
                                 "x\x00y", " x", "x ", "x.", "con|x", "a\nb"])
def test_name_refuses_anything_that_is_not_one_plain_name(bad):
    with pytest.raises(safe_paths.UnsafePath):
        safe_paths.name(bad)


@pytest.mark.parametrize("good", ["1001", "teacher_6de65185-716b-407e-a8ce-6d4028159f1d", "roster_preparatory.json",
                                  "HPC_Preparatory_template (3).xlsx", "20261027T073725123456Z.json", "2627"])
def test_name_keeps_ordinary_names(good):
    assert safe_paths.name(good) == good


def test_inside_stays_in_its_folder(tmp_path):
    assert safe_paths.inside(tmp_path, "a", "b.json") == tmp_path / "a" / "b.json"
    for parts in (("..", "x"), ("a", "..", "..", "x"), ("..\\..\\x",), (str(tmp_path.parent / "x"),)):
        with pytest.raises(safe_paths.UnsafePath):
            safe_paths.inside(tmp_path, *parts)


# ---------------------------------------------------------------------------
# The two attacks that were reproduced
# ---------------------------------------------------------------------------

@pytest.fixture
def world(monkeypatch, tmp_path):
    """A school admin and a teacher (cookie sessions), a fake PARAKH, and canary files of another account."""
    from backend import config
    from backend.main import app
    from backend.routers import activities_grid, class_template, hpc_cards as cards_router, teachers
    from backend.services import card_store, hpc_cards, hpc_sessions, own_activities, snapshots
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", data / "sessions")
    monkeypatch.setattr(card_store, "CARDS_DIR", data / "cards")
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", data / "snapshots")
    monkeypatch.setattr(own_activities, "OWN_DIR", data / "own_activities")

    stu = blank_student("PREPARATORY")
    portal = FakePortal({("PREPARATORY", "1001"): {"record": stu.record, "parts": stu.raw_parts}})
    for mod in (teachers, cards_router, activities_grid, class_template):
        monkeypatch.setattr(mod, "_portal", lambda teacher: portal, raising=False)
    monkeypatch.setattr(hpc_sessions, "portal_for", lambda *a, **k: portal)
    monkeypatch.setattr(hpc_cards, "lookups_for", lambda owner, client, stage: make_lookups("PREPARATORY", portal))

    import uuid
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    admin = TestClient(app, raise_server_exceptions=False)
    admin.headers.update(HDR)
    assert admin.post(f"{API}/auth/school/register", json={
        "udise_code": udise, "school_name": "Sweep School", "state": "Test", "district": "Test",
        "admin_name": "Sweep Admin", "admin_email": f"sweep.{tag}@example.com", "password": "secret123"}).status_code == 201
    assert admin.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"}).status_code == 200
    created = admin.post(f"{API}/school/teachers", json={"teacher_name": "Sweep Teacher", "username": f"sweep{tag}",
                                                         "password": "secret123", "assigned_stages": ["Preparatory"]}).json()
    teacher = TestClient(app, raise_server_exceptions=False)
    teacher.headers.update(HDR)
    assert teacher.post(f"{API}/auth/login", json={"identifier": f"sweep{tag}", "password": "secret123"}).status_code == 200
    school_id = admin.get(f"{API}/auth/me").json()["id"]

    own = data / "sessions" / f"teacher_{created['id']}"
    own.mkdir(parents=True)
    (own / "roster_preparatory.json").write_text(json.dumps([{"student_id": "1001", "student_name": "TEST STUDENT"}]),
                                                 encoding="utf-8")
    canaries = {}
    for rel in ("sessions/teacher_victim/session.json", "sessions/teacher_victim/roster_preparatory.json",
                "sessions/school_victim/session.json", "cards/teacher_victim/2627/preparatory/1001.json",
                "snapshots/teacher_victim/preparatory/1001/20260101T000000000000Z.json",
                "own_activities/teacher_victim.json", "canary.json"):
        p = data / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"access_token": SECRET, "values": {}, "version": 1, "parts": {}, "read_at": {}}),
                     encoding="utf-8")
        canaries[p] = p.read_bytes()
    outside = tmp_path / "outside.json"                      # outside the data folder altogether
    outside.write_text(json.dumps({"access_token": SECRET}), encoding="utf-8")
    canaries[outside] = outside.read_bytes()
    allowed = [data / "sessions" / f"teacher_{created['id']}", data / "sessions" / f"school_{school_id}",
               data / "cards" / f"teacher_{created['id']}", data / "snapshots" / f"teacher_{created['id']}",
               data / "own_activities"]
    return {"admin": admin, "teacher": teacher, "data": data, "canaries": canaries, "allowed": allowed,
            "outside": outside, "tmp": tmp_path}


def _escapes(world, before):
    """Canaries read/changed/deleted, or new files outside the account's own folders."""
    problems = [f"changed or deleted: {p}" for p, body in world["canaries"].items()
                if not p.exists() or p.read_bytes() != body]
    now = {p for p in world["tmp"].rglob("*") if p.is_file()}
    for p in now - before:
        if not any(a == p or a in p.parents for a in world["allowed"]):
            problems.append(f"new file outside the account: {p}")
    return problems


def test_school_roster_stage_cannot_read_another_accounts_file(world):
    r = world["admin"].get(f"{API}/school/roster", params={"stage": "..\\..\\..\\teacher_victim\\session"})
    assert r.status_code == 400 and SECRET not in r.text


def test_a_draft_cannot_delete_or_write_outside_the_teacher_folder(world):
    before = {p for p in world["tmp"].rglob("*") if p.is_file()}
    # preparatory_.. / 2627 / drafts / teacher_<id> / sessions: five steps up reach the data folder
    for sid in ("..\\..\\..\\..\\..\\..\\canary", "..\\..\\..\\..\\teacher_victim\\roster_preparatory"):
        assert world["teacher"].delete(f"{API}/teacher/hpc-cards/Preparatory/{sid}/draft").status_code in (400, 404)
        assert world["teacher"].put(f"{API}/teacher/hpc-cards/Preparatory/{sid}/draft",
                                    json={"values": {"a1_mother_tongue": "X"}}).status_code in (400, 404)
    assert _escapes(world, before) == []


def test_drafts_are_only_for_students_in_the_class_list(world):
    t = world["teacher"]
    assert t.put(f"{API}/teacher/hpc-cards/Preparatory/9999/draft", json={"values": {"a1_mother_tongue": "X"}}).status_code == 404
    assert t.put(f"{API}/teacher/hpc-cards/Preparatory/1001/draft", json={"values": {"a1_mother_tongue": "X"}}).status_code == 200
    r = t.put(f"{API}/teacher/hpc-cards/Preparatory/bulk", json={"field": "a1_mother_tongue", "values": {"9999": "X", "1001": "Y"}})
    assert r.status_code == 200 and r.json()["saved"] == ["1001"] and "9999" in r.json()["problems"]


# ---------------------------------------------------------------------------
# The sweep: every route, every traversal value
# ---------------------------------------------------------------------------

RAW = ["..", "...", "../x", "..\\x", "../../../../../../canary", "..\\..\\..\\..\\..\\..\\canary",
       "..\\..\\..\\teacher_victim\\session", "..\\..\\..\\..\\teacher_victim\\roster_preparatory",
       "/etc/passwd", "C:\\Windows\\win.ini", "x\x00y", "%2e%2e%2f", "%2e%2e%5c", "..%2f..%2f"]


def _values(world):
    return RAW + [str(world["outside"]), str(world["outside"].with_suffix(""))]


def _routes():
    import importlib
    out = []
    for m in ("auth", "schools", "teachers", "hpc_cards", "activity_library", "activities_grid", "class_template", "platform"):
        for r in importlib.import_module(f"backend.routers.{m}").router.routes:
            for method in r.methods:
                out.append((method, r.path, r))
    return out


def _body_for(path, method, value):
    """A body that puts the value where an id or file name goes."""
    if path.endswith("/draft") and method == "PUT":
        return {"values": {"a1_mother_tongue": "X"}}
    if path.endswith("/levels") and method == "PUT":
        return {"values": {value: {"c_PSLS1_awareness": "Proficient"}}}
    if path.endswith("/bulk") and method == "PUT":
        return {"field": "a1_mother_tongue", "values": {value: "X"}}
    if path.endswith("/import-upload"):
        return {"file_name": value, "apply": True}
    if path.endswith("/quick-fill"):
        return {"students": [value], "apply": False}
    if path.endswith("/activity-library/bulk"):
        return {"ids": [value], "action": "disable"}
    if path.startswith("/activity-library") and method in ("POST", "PATCH", "PUT"):
        return {"stage": value, "title": "x", "activity_id": value}
    if path.startswith("/activities-grid") or "/activities-grid/" in path:
        return {"values": {}}
    if path.endswith("/settings/{stage}"):
        return {"values": {}}
    return {}


DEFAULTS = {"stage": "Preparatory", "student_id": "1001"}     # ordinary values for the parts not being tried
QUERY_DEFAULTS = {"stage": "Preparatory", "field": "a1_mother_tongue", "file_name": "class.xlsx", "session": None}


def test_no_route_lets_a_traversal_value_leave_the_account_folder(world):
    sent, problems, swept = 0, [], set()
    for method, path, route in _routes():
        if path == "/auth/logout":
            continue
        params = [p.name for p in route.dependant.path_params]
        query = [p.name for p in route.dependant.query_params if p.name in ("stage", "file_name", "session", "field")]
        targets = [("path", p) for p in params] + [("query", q) for q in query] + [("body", None)]
        for kind, target in targets:
            for value in _values(world):
                for who in ("teacher", "admin"):
                    url_path = path
                    for p in params:
                        v = value if (kind, target) == ("path", p) else DEFAULTS.get(p, "x")
                        url_path = url_path.replace("{" + p + "}", quote(v, safe=""))
                    q = {k: (value if (kind, target) == ("query", k) else QUERY_DEFAULTS[k])
                         for k in query if (kind, target) == ("query", k) or QUERY_DEFAULTS.get(k) is not None}
                    kwargs = {"params": q}
                    if method in ("POST", "PUT", "PATCH"):
                        kwargs["json"] = _body_for(path, method, value if kind == "body" else "1001")
                    if path.endswith("/upload/validate"):
                        kwargs = {"params": q, "files": {"file": (f"{value}.xlsx", b"not a workbook")}}
                    before = {f for f in world["tmp"].rglob("*") if f.is_file()}
                    r = world[who].request(method, f"{API}{url_path}", **kwargs)
                    sent += 1
                    swept.add(path)
                    if SECRET in r.text:
                        problems.append(f"{method} {path} [{kind} {target}] {value!r} as {who}: answer has another account's data")
                    problems += [f"{method} {path} [{kind} {target}] {value!r} as {who}: {p}" for p in _escapes(world, before)]
    assert sent > 3000 and len(swept) >= 70
    assert problems == [], "\n".join(problems[:20])
