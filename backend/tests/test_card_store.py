"""The app's stored copy of cards, and the background check that keeps it in step with PARAKH (fake PARAKH)."""
import time

from backend.hpc import portal
from backend.services import card_store
from backend.services.card_store import start_check as real_start_check


class FakeCards:
    """Serves part formdata; `value` is what PARAKH holds now."""
    def __init__(self, value="old"):
        self.value, self.reads, self.fail = value, [], False

    def student(self, stage, student_id, hpc_col=None):
        if self.fail:
            raise RuntimeError("PARAKH did not answer")
        self.reads.append((student_id, hpc_col))
        return {"formdata": f"{self.value}-{student_id}"}


def wait(owner, stage="Preparatory"):
    for _ in range(200):
        view = card_store.check_view(owner, "2627", stage)
        if view and view["status"] != "RUNNING":
            return view
        time.sleep(0.01)
    raise AssertionError("check did not finish")


def test_a_change_made_on_parakh_is_found_and_the_copy_updated(monkeypatch):
    monkeypatch.setattr(card_store, "start_check", real_start_check)
    fake = FakeCards("old")
    raw, _ = card_store.class_parts(fake, "teacher_x", "2627", "Preparatory", ["1", "2"], ["part_c"])
    assert raw["1"]["part_c"] == "old-1" and len(fake.reads) == 2
    fake.value = "edited on the website"
    card_store.start_check(fake, "teacher_x", "2627", "Preparatory", ["1", "2"], ["part_c"])
    view = wait("teacher_x")
    assert view["status"] == "COMPLETED" and view["done"] == 2 and sorted(view["changed"]) == ["1", "2"]
    assert card_store.parts(fake, "teacher_x", "2627", "Preparatory", "1", ["part_c"])["part_c"] == "edited on the website-1"

    # the same parts are not checked again within CHECK_EVERY_SECONDS
    fake.reads.clear()
    again = card_store.start_check(fake, "teacher_x", "2627", "Preparatory", ["1", "2"], ["part_c"])
    assert again["id"] == view["id"] and fake.reads == []
    # another part is due on its own
    card_store.start_check(fake, "teacher_x", "2627", "Preparatory", ["1", "2"], ["part_b"])
    assert wait("teacher_x")["changed"] == [] and ("1", "part_b") in fake.reads


def test_no_change_reports_nothing_and_a_failed_check_keeps_the_copy_and_is_tried_again(monkeypatch):
    monkeypatch.setattr(card_store, "start_check", real_start_check)
    fake = FakeCards("same")
    card_store.class_parts(fake, "teacher_y", "2627", "Middle", ["7"], ["part_a1"])
    card_store.start_check(fake, "teacher_y", "2627", "Middle", ["7"], ["part_a1"])
    assert wait("teacher_y", "Middle")["changed"] == []

    card_store._checked_at.clear()
    fake.fail = True
    card_store.start_check(fake, "teacher_y", "2627", "Middle", ["7"], ["part_a1"])
    failed = wait("teacher_y", "Middle")
    assert failed["status"] == "FAILED" and "Could not check PARAKH" in failed["error"]
    fake.fail = False
    assert card_store.parts(fake, "teacher_y", "2627", "Middle", "7", ["part_a1"])["part_a1"] == "same-7"   # kept
    card_store.start_check(fake, "teacher_y", "2627", "Middle", ["7"], ["part_a1"])                        # due again
    assert wait("teacher_y", "Middle")["status"] == "COMPLETED"


def test_read_again_counts_as_checked():
    card_store._checked_at[("teacher_z", "2627", "preparatory", "part_c")] = 0
    card_store.forget("teacher_z", "2627", "Preparatory")
    assert time.time() - card_store._checked_at[("teacher_z", "2627", "preparatory", "part_c")] < 5


def test_request_pacing_is_shared_by_every_connection_of_one_login():
    a = portal.Portal(portal.Session(access_token="x", staff={"staff_id": 41}))
    b = portal.Portal(portal.Session(access_token="y", staff={"staff_id": 41}))
    c = portal.Portal(portal.Session(access_token="z", staff={"staff_id": 42}))
    assert a._pacer is b._pacer and a._pacer is not c._pacer


def test_a_background_read_waits_while_a_screen_is_loading(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(portal.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(portal.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    screen = portal.Portal(portal.Session(access_token="x", staff={"staff_id": 77}))
    screen._pace()                                     # a screen just asked
    asked = clock["t"]
    bg = card_store._background(screen)
    assert bg.background and not screen.background and bg._pacer is screen._pacer
    bg._pace()
    assert clock["t"] - asked >= 2.0                    # waited until the screen had been quiet for 2 s


def test_fetch_from_parakh_fills_the_copy_so_screens_read_nothing_more(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(card_store, "start_check", real_start_check)
    fetched = [SimpleNamespace(student_id=sid, raw_parts={"part_b": f"b-{sid}", "part_c": f"c-{sid}"}) for sid in ("1", "2")]
    card_store.put_many("teacher_f", "2627", "Preparatory", fetched)
    fake = FakeCards()
    raw, read_at = card_store.class_parts(fake, "teacher_f", "2627", "Preparatory", ["1", "2"], ["part_b", "part_c"])
    assert raw["2"] == {"part_b": "b-2", "part_c": "c-2"} and read_at and fake.reads == []
    assert card_store.start_check(fake, "teacher_f", "2627", "Preparatory", ["1", "2"], ["part_c"]) is None   # just read: no check


def test_warm_up_reads_only_what_is_missing():
    from types import SimpleNamespace
    card_store.put_many("teacher_w", "2627", "Middle", [SimpleNamespace(student_id="1", raw_parts={"part_b": "kept"})])
    fake = FakeCards()
    assert card_store.warm(fake, "teacher_w", "2627", "Middle", ["1", "2"], ["part_b", "part_c"])
    for _ in range(200):
        if ("teacher_w", "2627", "middle") not in card_store._warming:
            break
        time.sleep(0.01)
    assert sorted(fake.reads) == [("1", "part_c"), ("2", "part_b"), ("2", "part_c")]
    assert card_store.parts(fake, "teacher_w", "2627", "Middle", "1", ["part_b"])["part_b"] == "kept"


def test_the_fetch_runs_in_the_background_shows_progress_and_keeps_the_cards(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    from backend.routers import teachers as t
    monkeypatch.setattr(t, "_portal", lambda teacher: SimpleNamespace(ay="2627"))
    monkeypatch.setattr(t, "_stage", lambda teacher, stage: "Preparatory")
    monkeypatch.setattr(t, "teacher_stages", lambda teacher: ["Preparatory"])
    monkeypatch.setattr(t, "_workbook_path", lambda teacher: tmp_path / "w.xlsx")
    monkeypatch.setattr(t, "_roster_file", lambda teacher, name: tmp_path / f"r_{name}.json")
    seen = {}

    def export(client, stages, path, on_students, on_roster, on_each, **options):
        on_roster("Preparatory", [{"student_id": "9"}, {"student_id": "10"}])
        seen["early"] = json.loads((tmp_path / "r_Preparatory.json").read_text())    # the list is there at once
        on_each("Preparatory")
        seen["midway"] = t.sync_roster_status(teacher=teacher)["job"]
        on_each("Preparatory")
        on_students("Preparatory", [SimpleNamespace(student_id="9", raw_parts={"part_c": "c9"})])
        return path, {"Preparatory": [{"student_id": "9", "gender": "Male"}, {"student_id": "10", "gender": ""}]}
    monkeypatch.setattr(t.sync, "export_workbook", export)
    teacher = SimpleNamespace(id="T1")
    t._fetch_jobs.pop("T1", None)
    started = t.sync_roster(stage="Preparatory", teacher=teacher)
    assert started["status"] == "RUNNING"
    for _ in range(200):
        job = t.sync_roster_status(teacher=teacher)["job"]
        if job["status"] != "RUNNING":
            break
        time.sleep(0.01)
    assert job["status"] == "COMPLETED" and job["done"] == 2 and job["total"] == 2 and job["summary"] == "Preparatory: 2"
    assert len(seen["early"]) == 2 and seen["midway"]["done"] == 1 and seen["midway"]["total"] == 2
    assert json.loads((tmp_path / "r_Preparatory.json").read_text())[0]["gender"] == "Male"        # full details at the end
    fake = FakeCards()
    assert card_store.parts(fake, "teacher_T1", "2627", "Preparatory", "9", ["part_c"]) == {"part_c": "c9"} and fake.reads == []
