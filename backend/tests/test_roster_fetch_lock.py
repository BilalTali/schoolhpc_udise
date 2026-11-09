"""Pressing "Fetch from PARAKH" while a fetch is running must answer at once, and fetch once more afterwards.

Before the fix, sync_roster built the progress view while holding _fetch_lock, and the view takes the same lock:
a plain Lock taken twice by one thread waits for ever. Every progress poll then waited too, each holding a
database connection, until the pool (20 + 40) ran out and the whole app stopped answering (6 Nov 2026, server).
Teachers may be given a class at any time, so a Fetch pressed during a fetch runs once more when it ends.
"""
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend import database
from backend.routers import teachers

TEACHER = SimpleNamespace(id="t-lock-test", is_active=True)


@pytest.fixture
def fetch(monkeypatch):
    """A fetch that keeps 'reading PARAKH' until the test releases it; records the stages of every run."""
    state = SimpleNamespace(release=threading.Event(), runs=[], started=threading.Semaphore(0),
                            stages=["Preparatory"], teacher=TEACHER)

    def slow_fetch(job, teacher, client, stages):
        state.runs.append(list(stages))
        state.started.release()
        state.release.wait(10)
        with teachers._fetch_lock:
            job["status"] = "COMPLETED"

    @contextmanager
    def fake_session():
        yield SimpleNamespace(get=lambda model, key: state.teacher, expunge=lambda obj: None)

    monkeypatch.setattr(teachers, "_run_fetch", slow_fetch)
    monkeypatch.setattr(teachers, "_stage", lambda teacher, stage: stage or "Preparatory")
    monkeypatch.setattr(teachers, "teacher_stages", lambda teacher: list(state.stages))
    monkeypatch.setattr(teachers, "_portal", lambda teacher: SimpleNamespace(ay="2026-27"))
    monkeypatch.setattr(database, "SessionLocal", fake_session)
    teachers._fetch_jobs.pop(TEACHER.id, None)
    yield state
    state.release.set()
    teachers._fetch_jobs.pop(TEACHER.id, None)


def press(timeout=5):
    """POST /roster/sync in its own thread: a deadlock fails the test instead of hanging it."""
    answer = {}
    t = threading.Thread(target=lambda: answer.update(teachers.sync_roster(stage="Preparatory", teacher=TEACHER)),
                         daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "Fetch is stuck on _fetch_lock (deadlock)"
    return answer


def status():
    return teachers.sync_roster_status(teacher=TEACHER)["job"]


def wait_until(check, seconds=5):
    done = threading.Event()
    for _ in range(int(seconds / 0.05)):
        if check():
            return True
        done.wait(0.05)
    return False


def test_a_second_fetch_while_one_runs_answers_at_once(fetch):
    assert press()["status"] == "RUNNING" and fetch.started.acquire(timeout=5)
    second = press()
    assert second["status"] == "RUNNING" and second["again"] is True   # the running fetch's progress, flagged
    assert status()["status"] == "RUNNING"                              # progress polls are answered too
    assert len(fetch.runs) == 1                                          # no second fetch side by side


def test_fetch_pressed_during_a_fetch_runs_once_more_with_the_new_classes(fetch):
    press()
    assert fetch.started.acquire(timeout=5)
    press(); press()                                    # pressed twice more: still only one more fetch
    fetch.stages = ["Preparatory", "Middle"]            # the school gave the teacher a Middle class meanwhile
    fetch.release.set()
    assert fetch.started.acquire(timeout=5)             # the second fetch started on its own
    assert wait_until(lambda: status()["status"] == "COMPLETED" and not status()["again"])
    assert fetch.runs == [["Preparatory"], ["Preparatory", "Middle"]]


def test_when_the_second_fetch_cannot_start_the_page_stops_waiting(fetch):
    press()
    assert fetch.started.acquire(timeout=5)
    press()
    fetch.teacher = None                                # the teacher was removed meanwhile
    fetch.release.set()
    assert wait_until(lambda: status()["status"] == "COMPLETED" and status()["again"] is False)
    assert len(fetch.runs) == 1
