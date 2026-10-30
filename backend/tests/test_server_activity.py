"""The 'Server is working' strip: what reads a teacher's cards in the background, with its progress."""
from backend.services import card_store


def test_background_reads_and_rechecks_are_reported_with_their_progress(monkeypatch):
    monkeypatch.setattr(card_store, "_warming", {("teacher_t1", "2627", "middle"): {"done": 12, "total": 60},
                                                 ("teacher_t2", "2627", "middle"): {"done": 1, "total": 9}})
    monkeypatch.setattr(card_store, "_checks", {("teacher_t1", "2627", "preparatory"): {"status": "RUNNING", "done": 3, "total": 35},
                                                ("teacher_t1", "2627", "foundational"): {"status": "COMPLETED", "done": 21, "total": 21}})
    tasks = card_store.running_for("teacher_t1")
    assert {"kind": "reading", "stage": "middle", "done": 12, "total": 60} in tasks
    assert {"kind": "rechecking", "stage": "preparatory", "done": 3, "total": 35} in tasks
    assert len(tasks) == 2                                         # not another teacher's, not a finished check
