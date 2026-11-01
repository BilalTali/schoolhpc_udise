"""PARAKH connection status is what PARAKH says now, not just a saved file. PARAKH is MOCKED here."""
import pytest

from backend.hpc import portal


@pytest.fixture
def sessions(monkeypatch, tmp_path):
    from backend.services import hpc_sessions
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    hpc_sessions._LIVE.clear()
    return hpc_sessions


def _save(sessions, role="TEACHER"):
    sessions.save_session("teacher", "t1", portal.Session(access_token="a", refresh_token="r",
                                                         staff={"staff_id": 7, "name": "Fake Teacher", "role": role,
                                                                "hpc_stage": ["PREPARATORY"]}))


def test_a_session_parakh_refuses_shows_ended_and_is_removed(sessions, monkeypatch):
    _save(sessions)

    def refused(self, *a, **k):
        self.last_status = 401
        raise portal.PortalError("Portal session expired.")
    monkeypatch.setattr(portal.Portal, "roster_page", refused)
    st = sessions.status_of("teacher", "t1", check=True)
    assert st["logged_in"] is False and st["ended"] is True and "has ended" in st["reason"]
    assert sessions.load_session("teacher", "t1") is None                  # every screen now agrees: not connected
    assert sessions.status_of("teacher", "t1")["logged_in"] is False


def test_a_working_session_is_checked_and_the_answer_is_kept_for_a_while(sessions, monkeypatch):
    _save(sessions)
    calls = []
    monkeypatch.setattr(portal.Portal, "roster_page", lambda self, *a, **k: calls.append(1) or {})
    st = sessions.status_of("teacher", "t1", check=True)
    assert st["logged_in"] is True and st["checked"] is True
    sessions.status_of("teacher", "t1", check=True)
    assert len(calls) == 1                                                  # asked once, not on every page load
    _save(sessions)                                                         # a new session: asked afresh
    sessions.status_of("teacher", "t1", check=True)
    assert len(calls) == 2


def test_parakh_not_answering_is_said_and_the_session_kept(sessions, monkeypatch):
    _save(sessions)

    def down(self, *a, **k):
        self.last_status = None
        raise portal.PortalError("PARAKH did not answer (ConnectionError).")
    monkeypatch.setattr(portal.Portal, "roster_page", down)
    st = sessions.status_of("teacher", "t1", check=True)
    assert st["logged_in"] is True and st["checked"] is False and "Could not check" in st["reason"]
    assert sessions.load_session("teacher", "t1") is not None


def test_a_school_session_is_checked_with_the_school_list(sessions, monkeypatch):
    _save(sessions, role="SCHOOL")
    asked = []
    monkeypatch.setattr(portal.Portal, "school_hpc_page", lambda self, *a, **k: asked.append(a) or {})
    assert sessions.status_of("teacher", "t1", check=True)["checked"] is True and asked
