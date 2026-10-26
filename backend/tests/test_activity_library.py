"""Activity Library: sync from a fake PARAKH (no network), browsing, edits, defaults, sharing, permissions."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.hpc.portal import PortalError
from backend.main import app
from backend.models.library import AuditLog, LibraryActivity
from backend.routers import activity_library as router_mod
from backend.services import activity_library as lib

client = TestClient(app)
API = "/api/v1"
REAL_CLIENT = router_mod._client

SUBJECT_IDS = {"Foundational": (1, ["FSDOM1", "FSDOM2", "FSDOM3", "FSDOM4", "FSDOM5", "FSDOM51"]),
               "Preparatory": (88, [f"PSLS{i}" for i in range(1, 8)]),
               "Middle": (269, ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"])}


def bank_record(portal_id, stage, caption, pictures=False, subject=0, text="Pairs act out a short conversation."):
    first, codes = SUBJECT_IDS[stage]
    dt = {"gl": ["CG1"], "cpt": ["C1.1"], "desc": [text, "What did you say?"], "approaches": [], "any-other": "",
          "awr": ["a-b", "a-p", "a-a", ""], "sen": ["s-b", "s-p", "s-a", ""], "cre": ["c-b", "c-p", "c-a", ""],
          "img": ["x.png", "", "", ""] if pictures else ["", "", "", ""]}
    return {"id": portal_id, "activity_caption": caption, "hpc_stage": stage.upper(), "grade_id": 7,
            "domain_ids": [first + subject], "is_active": True, "used_counter": 5, "created_on": "01/04/2026",
            "activity_data_json": json.dumps({"nm": caption, "dt": dt})}


class FakeBankPortal:
    """The three read-only Activity Bank calls; records per stage, optional failures."""

    def __init__(self, records=None, mine=None):
        self.records = list(records or [])
        self.mine = list(mine or [])
        self.fail_on_page = None          # (stage, page) -> raise PortalError
        self.transient = 0                # fail this many calls, then work
        self.calls = []

    def activity_categories(self, stage):
        first, codes = SUBJECT_IDS[stage]
        return [{"id": first + i, "ent_code": c, "ent_caption": c} for i, c in enumerate(codes)]

    def _page(self, records, stage, page_no, page_size):
        self.calls.append((stage, page_no))
        if self.transient:
            self.transient -= 1
            raise PortalError("Portal returned HTTP 502 (not JSON)")
        if self.fail_on_page == (stage, page_no):
            raise PortalError("GET /country/activities failed (HTTP 500).")
        rows = [r for r in records if r["hpc_stage"] == stage.upper()]
        return {"records": rows[(page_no - 1) * page_size: page_no * page_size], "count": len(rows), "page_no": page_no}

    def activity_bank_page(self, page_no=1, page_size=200, stage=None):
        return self._page(self.records, stage, page_no, page_size)

    def my_activities_page(self, stage, page_no=1, page_size=200):
        return self._page(self.mine, stage, page_no, page_size)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(lib, "_sleep", lambda s: None)


@pytest.fixture
def world(monkeypatch):
    """Two schools; school A has an admin and two teachers. Every PARAKH call goes to `fake`."""
    tag = uuid.uuid4().hex[:8]
    users = {}
    for school in ("a", "b"):
        udise = str(uuid.uuid4().int)[:11]
        client.post(f"{API}/auth/school/register", json={
            "udise_code": udise, "school_name": f"School {school}", "state": "JK", "district": "Budgam",
            "admin_name": f"Admin {school}", "admin_email": f"{school}{tag}@example.com", "password": "secret123"})
        token = client.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"}).json()["access_token"]
        users[f"admin_{school}"] = {"Authorization": f"Bearer {token}"}
    for name in ("t1", "t2"):
        username = f"{name}{tag}"
        client.post(f"{API}/school/teachers", headers=users["admin_a"], json={
            "teacher_name": name.upper(), "username": username, "password": "secret123",
            "assigned_stages": ["Preparatory", "Middle"]})
        token = client.post(f"{API}/auth/login", json={"identifier": username, "password": "secret123"}).json()["access_token"]
        users[name] = {"Authorization": f"Bearer {token}"}
    fake = FakeBankPortal()
    monkeypatch.setattr(router_mod, "_client", lambda db, actor: fake)
    with SessionLocal() as db:                       # each test starts from an empty shared cache
        db.query(LibraryActivity).delete()
        db.commit()
    return users, fake


def sync(headers, stage=None):
    res = client.post(f"{API}/activity-library/sync", json={"stage": stage} if stage else {}, headers=headers)
    assert res.status_code == 202, res.text
    return client.get(f"{API}/activity-library/sync/{res.json()['id']}", headers=headers).json()


def items(headers, stage="Preparatory", **params):
    res = client.get(f"{API}/activity-library", params={"stage": stage, "page_size": 500, **params}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def numbers(counts):
    """A sync's counts without the list of changes shown to the admin."""
    return {k: v for k, v in counts.items() if k != "changed"}


def by_code(listing, code):
    return next(i for i in listing["items"] if i["code"] == code)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def test_sync_new_updated_removed_and_restored(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "L1CG 1, C 1.1"), bank_record(2, "Preparatory", "MCG 1, C 1.2"),
                    bank_record(3, "Middle", "SCCG 1, C 1.1"), bank_record(4, "Middle", "SCCG 1, C 1.2")]
    job = sync(users["admin_a"])
    assert job["status"] == "COMPLETED" and job["progress"] == 100
    assert numbers(job["counts"]["Preparatory"]) == {"new": 2, "updated": 0, "removed": 0, "unchanged": 0}
    assert sorted(c["change"] for c in job["counts"]["Preparatory"]["changed"]) == ["new", "new"]   # shown to the admin
    assert job["counts"]["Middle"]["new"] == 2 and job["counts"]["Foundational"]["new"] == 0

    fake.records[0] = bank_record(1, "Preparatory", "L1CG 1, C 1.1", text="Changed upstream.")
    fake.records[0]["used_counter"] = 999           # usage counts alone are not a change
    fake.records[1]["used_counter"] = 1000
    del fake.records[2]
    job = sync(users["admin_a"])
    assert numbers(job["counts"]["Preparatory"]) == {"new": 0, "updated": 1, "removed": 0, "unchanged": 1}
    assert job["counts"]["Middle"]["removed"] == 1

    middle = items(users["admin_a"], "Middle")
    gone = by_code(middle, "SCCG 1, C 1.1")          # kept, marked, and no longer offered in Excel
    assert gone["upstream_status"] == "removed" and gone["usable_in_excel"] is False
    assert items(users["admin_a"], "Middle", upstream="removed")["total"] == 1

    fake.records.append(bank_record(3, "Middle", "SCCG 1, C 1.1"))
    assert sync(users["admin_a"], "Middle")["counts"]["Middle"]["updated"] == 1
    assert by_code(items(users["admin_a"], "Middle"), "SCCG 1, C 1.1")["upstream_status"] == "present"


def test_failed_sync_keeps_the_old_library(world):
    users, fake = world
    fake.records = [bank_record(i, "Preparatory", f"A {i}") for i in range(1, 251)]   # three pages
    assert sync(users["admin_a"], "Preparatory")["status"] == "COMPLETED"
    before = items(users["admin_a"])["total"]

    fake.records = fake.records[:10]                 # would mark 240 as removed...
    fake.fail_on_page = ("Preparatory", 1)           # ...but the read fails
    job = sync(users["admin_a"], "Preparatory")
    assert job["status"] == "FAILED" and "HTTP 500" in job["error"] and "not changed" in job["step"]
    listing = items(users["admin_a"])
    assert listing["total"] == before and listing["counts"]["removed"] == 0

    fake.fail_on_page = None
    fake.records = []                                # an empty answer is treated as a portal problem
    job = sync(users["admin_a"], "Preparatory")
    assert job["status"] == "FAILED" and "returned no Preparatory activities" in job["error"]
    assert items(users["admin_a"])["counts"]["removed"] == 0


def test_sync_retries_and_large_list_order(world):
    users, fake = world
    # 600 activities over six pages; codes chosen so natural order differs from text order
    fake.records = [bank_record(i, "Preparatory", f"CG 1, C 1.{i}") for i in range(1, 601)]
    fake.transient = 2                               # two failures, then the retry works
    job = sync(users["admin_a"], "Preparatory")
    assert job["status"] == "COMPLETED" and job["counts"]["Preparatory"]["new"] == 600
    assert fake.calls[:3] == [("Preparatory", 1)] * 3 and {p for _, p in fake.calls} == set(range(1, 7))
    codes = [e["label"] for e in client.get(f"{API}/activity-library/dropdown/Preparatory",
                                            headers=users["admin_a"]).json()["entries"]]
    assert len(codes) == 600
    assert codes[:3] == ["CG 1, C 1.1 (#P1)", "CG 1, C 1.2 (#P2)", "CG 1, C 1.3 (#P3)"]
    assert codes.index("CG 1, C 1.10 (#P10)") == 9   # 1.10 after 1.9, not after 1.1


def test_refused_requests_are_not_retried(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    fake.fail_on_page = ("Preparatory", 1)
    original = FakeBankPortal._page

    def refuse(self, records, stage, page_no, page_size):
        self.calls.append((stage, page_no))
        raise PortalError("GET /country/activities failed (HTTP 422).")
    FakeBankPortal._page = refuse
    try:
        job = sync(users["admin_a"], "Preparatory")
    finally:
        FakeBankPortal._page = original
    assert job["status"] == "FAILED" and "HTTP 422" in job["error"] and len(fake.calls) == 1


def test_duplicate_codes_across_stages(world):
    users, fake = world
    fake.records = [bank_record(10, "Preparatory", "MCG1, C-1.1"), bank_record(11, "Middle", "MCG1, C-1.1")]
    fake.records.append(bank_record(12, "Middle", "Dance &amp;amp; Movement  C-3.2"))
    sync(users["admin_a"])
    prep = client.get(f"{API}/activity-library/dropdown/Preparatory", headers=users["admin_a"]).json()["entries"]
    mid = client.get(f"{API}/activity-library/dropdown/Middle", headers=users["admin_a"]).json()["entries"]
    assert [e["key"] for e in prep] == ["P10"] and [e["key"] for e in mid] == ["P12", "P11"]
    assert mid[0]["label"] == "Dance & Movement C-3.2 (#P12)"


def test_sync_needs_a_portal_session_and_runs_once(world, monkeypatch):
    users, fake = world
    monkeypatch.setattr(router_mod, "_client", REAL_CLIENT)     # the real session lookup: no session saved
    res = client.post(f"{API}/activity-library/sync", json={}, headers=users["admin_a"])
    assert res.status_code == 401 and "session" in res.json()["detail"].lower()

    with SessionLocal() as db:
        school_id = client.get(f"{API}/auth/me", headers=users["admin_a"]).json()["id"]
        actor = lib.Actor("SCHOOL_ADMIN", school_id, school_id)
        job, running = lib.start_sync(db, actor, ["Preparatory"])
        again, running2 = lib.start_sync(db, actor, ["Middle"])
        assert not running and running2 and again.id == job.id
        assert lib.recover_interrupted_syncs() >= 1


def test_only_the_school_admin_fetches_from_parakh_and_teachers_get_the_copy(world):
    users, fake = world
    fake.records = [bank_record(1, "Middle", "SCCG 1, C 1.1")]
    res = client.post(f"{API}/activity-library/sync", json={"stage": "Middle"}, headers=users["t1"])
    assert res.status_code == 403 and "school admin" in res.text
    job = sync(users["admin_a"], "Middle")
    assert job["status"] == "COMPLETED" and job["counts"]["Middle"]["new"] == 1
    assert by_code(items(users["t1"], "Middle"), "SCCG 1, C 1.1")["usable_in_excel"]      # teachers: from the app's copy
    listing = items(users["t1"], "Middle")
    assert "Middle" in listing["sync"]["bank_updated"]

    # what every teacher screen's lists now read instead of PARAKH's bank
    bank = lib.bank_activities("MIDDLE")
    assert bank[1]["activity_caption"] == "SCCG 1, C 1.1" and bank[1]["content"]["dt"]["desc"][0].startswith("Pairs")
    from backend.hpc.stages import common
    assert common.ACTIVITY_SOURCE is lib.bank_activities


class _NoBankPortal:
    """Answers the small lists Lookups needs; the Activity Bank must not be asked for."""
    state, district_id, school_id = "jk", 2, 1

    def _request(self, method, path, **kwargs):
        if "categories/MED_INST" in path:
            return {"data": {"MED_INST": [], "LOCATION": []}}
        if "sections" in path:
            return {"data": {"records": []}}
        return {"data": {} if "grades" in path else []}

    def activity_categories(self, stage_code):
        return []

    def activity_bank_page(self, *args):
        raise AssertionError("Lookups asked PARAKH for the Activity Bank")


def test_lookups_read_activities_from_the_app_not_from_parakh(world):
    users, fake = world
    fake.records = [bank_record(7, "Preparatory", "From the copy")]
    sync(users["admin_a"], "Preparatory")
    from backend.hpc.stages.common import Lookups
    lk = Lookups(_NoBankPortal(), "PREPARATORY")
    assert lk.activities[7]["activity_caption"] == "From the copy" and lk.activity_label(7) == "7: From the copy"


def test_automatic_update_runs_once_a_day_with_the_admins_session(world, monkeypatch):
    import time as _time
    from datetime import datetime
    from backend.models.library import ActivitySyncJob
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    school_id = client.get(f"{API}/auth/me", headers=users["admin_a"]).json()["id"]
    school_id_b = client.get(f"{API}/auth/me", headers=users["admin_b"]).json()["id"]
    with SessionLocal() as db:                      # make every stage's copy older than a day
        db.query(LibraryActivity).delete()
        db.query(ActivitySyncJob).filter(ActivitySyncJob.started_by == "auto").delete()
        db.commit()
    monkeypatch.setattr(fake, "my_activities_page", lambda *a: (_ for _ in ()).throw(AssertionError("not for the admin")),
                        raising=False)

    def no_session(school):
        from fastapi import HTTPException
        raise HTTPException(401, "not connected")
    assert lib.maybe_auto_sync(school_id, client_for=no_session) is None              # not connected: nothing
    job_id = lib.maybe_auto_sync(school_id, client_for=lambda school: fake)
    assert job_id
    for _ in range(100):
        with SessionLocal() as db:
            job = db.get(ActivitySyncJob, job_id)
            if job.status in ("COMPLETED", "FAILED"):
                break
        _time.sleep(0.05)
    assert job.status == "COMPLETED" and job.started_by == "auto", job.error
    assert job.counts["Preparatory"]["changed"] == [{"code": "A", "change": "new"}]
    assert lib.maybe_auto_sync(school_id, client_for=lambda school: fake) is None     # one automatic try a day

    with SessionLocal() as db:                      # Preparatory fresh; the other stages are still due
        for a in db.query(LibraryActivity).all():
            a.last_synced_at = datetime.utcnow()
        db.commit()
    with SessionLocal() as db:
        assert lib.stale_stages(db) == ["Foundational", "Middle"]          # Preparatory was just updated
    assert lib.auto_sync_tick(session_exists=lambda school_id: school_id == school_id_b) == []   # B has no session


# ---------------------------------------------------------------------------
# Editing, defaults, coverage
# ---------------------------------------------------------------------------

def test_edit_diff_and_reset(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "L1CG 1, C 1.1")]
    sync(users["admin_a"])
    act = items(users["admin_a"])["items"][0]
    assert act["edited"] is False and act["covers_all"] is True and act["portal_subject_names"] == ["Language 1 (R1)"]

    url = f"{API}/activity-library/{act['id']}"
    res = client.patch(url, headers=users["admin_a"], json={
        "activity_text": "Our version.", "rubric": {"awareness": {"beginner": "Ours"}},
        "display_name": "Asking politely", "version": act["version"]})
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["edited"] and d["activity_text"] == "Our version." and d["label"] == "L1CG 1, C 1.1 - Asking politely"
    assert {x["field"] for x in d["diff"]} == {"activity_text", "rubric.awareness.beginner"}
    assert d["original"]["activity_text"] == "Pairs act out a short conversation."

    # a second edit keeps the first rubric edit, and a stale version is refused
    d2 = client.patch(url, headers=users["admin_a"], json={"rubric": {"awareness": {"proficient": "Ours too"}},
                                                           "version": d["version"]}).json()
    assert d2["rubric"]["awareness"] == {"beginner": "Ours", "proficient": "Ours too", "advanced": "a-a"}
    assert client.patch(url, headers=users["admin_a"], json={"activity_text": "x", "version": d["version"]}).status_code == 409

    # other schools never see school A's edits
    other = by_code(items(users["admin_b"]), "L1CG 1, C 1.1")
    assert other["edited"] is False and other["activity_text"] == "Pairs act out a short conversation."

    reset = client.post(f"{url}/reset", headers=users["admin_a"]).json()
    assert reset["edited"] is False and reset["diff"] == [] and reset["title"] == "Asking politely"
    assert any(h["action"] == "reset" for h in reset["history"])

    # editing a text back to the original is not an edit
    client.patch(url, headers=users["admin_a"], json={"activity_text": "Changed."})
    back = client.patch(url, headers=users["admin_a"], json={"activity_text": "Pairs act out a short conversation."}).json()
    assert back["edited"] is False


def test_coverage_badge_and_filter(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A"), bank_record(2, "Preparatory", "B")]
    sync(users["admin_a"])
    a = by_code(items(users["admin_a"]), "A")
    d = client.patch(f"{API}/activity-library/{a['id']}", headers=users["admin_a"],
                     json={"subjects": ["PSLS1", "PSLS2", "PSLS4", "PSLS6", "PSLS7"]}).json()
    assert d["covers_all"] is False and d["missing_subjects"] == ["Mathematics", "Art Education"]
    assert [i["code"] for i in items(users["admin_a"], covers_all=False)["items"]] == ["A"]
    assert [i["code"] for i in items(users["admin_a"], covers_all=True)["items"]] == ["B"]
    assert [i["code"] for i in items(users["admin_a"], subject="PSLS3")["items"]] == ["B"]
    assert [i["code"] for i in items(users["admin_a"], q="art education")["items"]] == ["B"]
    bad = client.patch(f"{API}/activity-library/{a['id']}", headers=users["admin_a"], json={"subjects": ["SM"]})
    assert bad.status_code == 422 and "Unknown subject" in bad.json()["detail"]


def test_default_must_cover_all_subjects(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A"), bank_record(2, "Preparatory", "B"),
                    bank_record(3, "Preparatory", "C", pictures=True)]
    sync(users["admin_a"])
    a, b, c = (by_code(items(users["admin_a"]), x) for x in "ABC")
    client.patch(f"{API}/activity-library/{a['id']}", headers=users["admin_a"], json={"subjects": ["PSLS1"]})

    url = f"{API}/activity-library/defaults/Preparatory"
    res = client.put(url, headers=users["admin_a"], json={"activity_id": a["id"]})
    assert res.status_code == 409 and len(res.json()["detail"]["missing_subjects"]) == 6
    assert client.put(url, headers=users["admin_a"], json={"activity_id": a["id"], "confirm_partial": True}).json()["covers_all"] is False
    assert client.put(url, headers=users["admin_a"], json={"activity_id": c["id"]}).status_code == 422   # has pictures
    assert client.put(url, headers=users["admin_a"], json={"activity_id": b["id"]}).json()["covers_all"] is True

    listing = items(users["admin_a"])
    assert listing["default_id"] == b["id"] and listing["items"][0]["code"] == "B"     # default first
    assert client.get(f"{API}/activity-library/dropdown/Preparatory", headers=users["admin_a"]).json()["entries"][0]["key"] == "P2"
    assert client.put(url, headers=users["t1"], json={"activity_id": b["id"]}).status_code == 403

    # turning the default off clears it
    client.patch(f"{API}/activity-library/{b['id']}", headers=users["admin_a"], json={"status": "disabled"})
    assert client.get(url, headers=users["admin_a"]).json()["activity_id"] is None


def test_disabled_and_picture_activities_leave_the_dropdown(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A"), bank_record(2, "Preparatory", "B"),
                    bank_record(3, "Preparatory", "C", pictures=True)]
    sync(users["admin_a"])
    ids = {i["code"]: i["id"] for i in items(users["admin_a"])["items"]}
    keys = lambda h: [e["key"] for e in client.get(f"{API}/activity-library/dropdown/Preparatory", headers=h).json()["entries"]]
    assert keys(users["admin_a"]) == ["P1", "P2"]
    assert "pictures" in by_code(items(users["admin_a"]), "C")["not_usable_reason"]

    res = client.post(f"{API}/activity-library/bulk", headers=users["admin_a"], json={"ids": [ids["A"]], "action": "disable"})
    assert res.status_code == 200
    assert keys(users["admin_a"]) == ["P2"] and keys(users["t1"]) == ["P2"]      # the teacher's dropdown too
    assert keys(users["admin_b"]) == ["P1", "P2"]                                 # other schools unaffected
    assert client.post(f"{API}/activity-library/bulk", headers=users["t1"], json={"ids": [ids["A"]], "action": "enable"}).status_code == 403
    client.post(f"{API}/activity-library/bulk", headers=users["admin_a"], json={"ids": [ids["A"]], "action": "enable"})
    assert keys(users["admin_a"]) == ["P1", "P2"]
    assert items(users["admin_a"], status="disabled")["total"] == 0


# ---------------------------------------------------------------------------
# Activities made in this app, sharing, permissions, audit
# ---------------------------------------------------------------------------

def test_teacher_activity_sharing_needs_consent(world):
    users, fake = world
    res = client.post(f"{API}/activity-library", headers=users["t1"], json={
        "stage": "Preparatory", "title": "Story circle", "activity_text": "Children retell a story."})
    assert res.status_code == 201, res.text
    act = res.json()
    assert act["source"] == "local" and act["share_state"] == "private" and act["covers_all"] is True
    assert act["usable_in_excel"] is False and "Not finished yet" in act["not_usable_reason"]
    assert "Curricular goal" in act["not_usable_reason"]
    assert "Curricular goal" in act["portal_ready"]["missing"]
    url = f"{API}/activity-library/{act['id']}"

    codes = lambda h: [i["code"] for i in items(h)["items"]]
    assert "Story circle" in codes(users["t1"]) and "Story circle" in codes(users["admin_a"])
    assert "Story circle" not in codes(users["t2"]) and "Story circle" not in codes(users["admin_b"])

    assert client.post(f"{url}/share", headers=users["t1"], json={"level": "school"}).status_code == 422
    assert client.post(f"{url}/share", headers=users["admin_a"], json={"level": "school", "consent": True}).status_code == 403
    assert client.post(f"{url}/share", headers=users["t1"], json={"level": "school", "consent": True}).status_code == 200
    assert "Story circle" in codes(users["t2"])
    assert client.patch(url, headers=users["t2"], json={"activity_text": "Mine now"}).status_code == 403

    shared = client.post(f"{url}/share", headers=users["t1"], json={"level": "community", "consent": True}).json()
    assert shared["share_state"] == "community"
    assert "Story circle" not in codes(users["admin_b"])          # waits for the platform admin's review
    with SessionLocal() as db:
        row = db.get(LibraryActivity, act["id"])
        assert row.share_consent_text == lib.CONSENT_TEXT and row.share_consent_by.startswith("teacher:")
        row.share_state = "community_ok"
        db.commit()
    assert "Story circle" in codes(users["admin_b"])
    assert client.delete(url, headers=users["admin_b"]).status_code == 403    # other schools may use it, not delete it

    # the teacher can stop sharing at any time, and delete their own activity
    assert client.post(f"{url}/share", headers=users["t1"], json={"level": "private"}).json()["share_state"] == "private"
    assert "Story circle" not in codes(users["admin_b"])
    assert client.delete(url, headers=users["t2"]).status_code == 404
    assert client.delete(url, headers=users["t1"]).status_code == 204


def test_permissions_and_portal_rules(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    sync(users["admin_a"])
    a = by_code(items(users["t1"]), "A")
    assert a["can_edit"] is True and a["edit_scope"] == "me" and a["can_manage"] is False
    url = f"{API}/activity-library/{a['id']}"
    assert client.patch(url, headers=users["t1"], json={"status": "disabled"}).status_code == 403
    assert client.post(f"{url}/reset", headers=users["t1"]).status_code == 200          # nothing of theirs to reset
    assert client.delete(url, headers=users["admin_a"]).status_code == 400       # PARAKH activities: turn off instead
    assert client.get(f"{API}/activity-library/{uuid.uuid4()}", headers=users["t1"]).status_code == 404
    assert client.get(f"{API}/activity-library", params={"stage": "Secondary"}, headers=users["t1"]).status_code == 400
    assert TestClient(app).get(f"{API}/activity-library", params={"stage": "Preparatory"}).status_code == 401

    # a teacher may copy a PARAKH activity and change the copy
    copy_ = client.post(f"{url}/duplicate", headers=users["t1"]).json()
    assert copy_["source"] == "local" and copy_["title"].startswith("Copy of A") and copy_["activity_text"] == a["activity_text"]
    renamed = client.patch(f"{API}/activity-library/{copy_['id']}", headers=users["t1"],
                           json={"title": "Our role play", "version": copy_["version"]})
    assert renamed.status_code == 422 and "cannot be changed" in renamed.text    # cards find it by its name
    edited = client.patch(f"{API}/activity-library/{copy_['id']}", headers=users["t1"],
                          json={"subjects": ["PSLS1"], "activity_text": "Our way", "version": copy_["version"]}).json()
    assert edited["title"] == copy_["title"] and edited["activity_text"] == "Our way"
    assert edited["missing_subjects"][0] == "Language 2 (R2)"
    assert client.post(f"{API}/activity-library/{copy_['id']}/reset", headers=users["admin_a"]).status_code == 400

    too_long = client.post(f"{API}/activity-library", headers=users["t1"],
                           json={"stage": "Preparatory", "title": "x" * 201})
    assert too_long.status_code == 422
    assert client.post(f"{API}/activity-library", headers=users["t1"], json={"stage": "Preparatory", "title": "  "}).status_code == 422

    with SessionLocal() as db:
        actions = {r.action for r in db.query(AuditLog).filter(AuditLog.entity_id.in_([a["id"], copy_["id"]])).all()}
    assert {"create", "duplicate", "edit"} <= actions


def test_sync_status_reports_last_sync_per_stage(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    sync(users["admin_a"], "Preparatory")
    status_ = client.get(f"{API}/activity-library/sync/status", headers=users["admin_a"]).json()
    assert status_["latest"]["status"] == "COMPLETED" and "Preparatory" in status_["last_synced"]
    assert "Middle" not in status_["last_synced"]
    other = client.get(f"{API}/activity-library/sync/{status_['latest']['id']}", headers=users["admin_b"])
    assert other.status_code == 404                  # another school's job


# ---------------------------------------------------------------------------
# Teachers edit any activity; activities made here are used on cards
# ---------------------------------------------------------------------------

def _teacher_id(headers):
    return client.get(f"{API}/auth/me", headers=headers).json()["id"]


def test_teacher_edits_a_parakh_activity_for_their_own_students(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    sync(users["admin_a"])
    a = by_code(items(users["t1"]), "A")
    url = f"{API}/activity-library/{a['id']}"
    res = client.patch(url, headers=users["t1"], json={
        "activity_text": "Our way of doing it", "assessment_text": "New question?",
        "rubric": {"awareness": {"beginner": "new b"}}, "version": a["version"]})
    assert res.status_code == 200, res.text
    mine = res.json()
    assert mine["activity_text"] == "Our way of doing it" and mine["assessment_text"] == "New question?"
    assert mine["rubric"]["awareness"]["beginner"] == "new b" and mine["rubric"]["awareness"]["proficient"] == "a-p"
    assert mine["edited_by_me"] and mine["modified"] and mine["can_reset"] and mine["usable_in_excel"]
    # only this teacher's version: the other teacher and the school keep PARAKH's text
    assert by_code(items(users["t2"]), "A")["activity_text"] == "Pairs act out a short conversation."
    assert by_code(items(users["admin_a"]), "A")["edited"] is False
    assert client.patch(url, headers=users["t1"], json={"activity_text": "x", "version": a["version"]}).status_code == 409

    resolve = lib.resolver_for_teacher(_teacher_id(users["t1"]), "Preparatory")
    entry = resolve("P1")
    assert entry["modified"] is True and entry["content"]["desc"][0] == "Our way of doing it"
    assert resolve.typed == {"A": "P1"}                     # an edited one goes on cards as manual, found by name
    assert entry["content"]["awr"][:3] == ["new b", "a-p", "a-a"] and entry["content"]["gl"] == ["CG1"]
    assert lib.resolver_for_teacher(_teacher_id(users["t2"]), "Preparatory")("P1")["modified"] is False

    # the school admin's edit is the base; the teacher's own edit stays on top; reset goes back to the school's
    client.patch(url, headers=users["admin_a"], json={"assessment_text": "School question?"})
    assert by_code(items(users["t2"]), "A")["assessment_text"] == "School question?"
    assert by_code(items(users["t1"]), "A")["assessment_text"] == "New question?"
    after = client.post(f"{url}/reset", headers=users["t1"]).json()
    assert after["activity_text"] == "Pairs act out a short conversation." and after["assessment_text"] == "School question?"
    assert after["edited_by_me"] is False and after["edited_by_school"] is True
    with SessionLocal() as db:
        actions = {r.action for r in db.query(AuditLog).filter(AuditLog.entity_id == a["id"]).all()}
    assert {"edit_own", "reset_own"} <= actions


def test_activity_made_here_is_usable_once_finished_and_codes_come_from_parakh(world):
    users, fake = world
    fake.records = [bank_record(1, "Preparatory", "A")]
    sync(users["admin_a"])
    codes = client.get(f"{API}/activity-library/codes/Preparatory", headers=users["t1"]).json()
    assert codes["goals"] == [{"code": "CG1", "used_by": 1}] and codes["competencies"][0]["code"] == "C1.1"

    rubric = {a: {"beginner": f"{a} b", "proficient": f"{a} p", "advanced": f"{a} a"}
              for a in ("awareness", "sensitivity", "creativity")}
    body = {"stage": "Preparatory", "title": "Story circle", "activity_text": "Children retell a story.",
            "assessment_text": "Can you tell it again?", "rubric": rubric, "goals": ["CG1"], "competencies": ["ZZ9"]}
    bad = client.post(f"{API}/activity-library", headers=users["t1"], json=body)
    assert bad.status_code == 422 and "ZZ9" in bad.text
    act = client.post(f"{API}/activity-library", headers=users["t1"], json={**body, "competencies": ["C1.1"]}).json()
    assert act["usable_in_excel"] is True and act["portal_ready"]["ok"]
    key = f"L{act['id']}"
    dropdown = client.get(f"{API}/activity-library/dropdown/Preparatory", headers=users["t1"]).json()["entries"]
    assert key in {e["key"] for e in dropdown}
    resolve = lib.resolver_for_teacher(_teacher_id(users["t1"]), "Preparatory")
    assert resolve(key)["portal_id"] is None and resolve(key)["caption"] == "Story circle"
    assert resolve.typed == {"Story circle": key}

    # Middle needs the approach as well
    mid = client.post(f"{API}/activity-library", headers=users["t1"], json={**body, "stage": "Middle", "competencies": []})
    assert "Approach" in mid.json()["portal_ready"]["missing"]
    fixed = client.patch(f"{API}/activity-library/{mid.json()['id']}", headers=users["t1"],
                         json={"approaches": [5], "version": mid.json()["version"]}).json()
    assert "Approach (any other) text" in fixed["portal_ready"]["missing"]
    assert client.patch(f"{API}/activity-library/{mid.json()['id']}", headers=users["t1"],
                        json={"approaches": [9]}).status_code == 422
