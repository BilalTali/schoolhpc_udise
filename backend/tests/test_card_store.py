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
