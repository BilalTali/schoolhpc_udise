"""L-12: PARAKH session tokens are encrypted on disk with the app key; uploaded workbooks are kept 30 days."""
import json
import os
import time

import pytest

from backend.hpc import portal

TOKEN = "made-up-parakh-access-token"


@pytest.fixture
def sessions(monkeypatch, tmp_path):
    from backend.services import hpc_sessions
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    return hpc_sessions


def _session():
    return portal.Session(access_token=TOKEN, refresh_token="made-up-refresh", staff={"staff_id": 7, "name": "Fake Teacher"})


def test_a_saved_session_is_encrypted_and_reads_back(sessions):
    sessions.save_session("teacher", "t1", _session())
    raw = sessions.session_path("teacher", "t1").read_text(encoding="utf-8")
    assert TOKEN not in raw and "made-up-refresh" not in raw and raw.startswith("enc:v1:")
    back = sessions.load_session("teacher", "t1")
    assert back.access_token == TOKEN and back.staff["name"] == "Fake Teacher"
    assert sessions.status_of("teacher", "t1")["logged_in"] is True


def test_a_session_saved_before_encryption_still_works_and_is_encrypted_on_first_read(sessions):
    path = sessions.session_path("teacher", "old")
    path.write_text(json.dumps(_session().__dict__), encoding="utf-8")          # the old plain file
    assert sessions.load_session("teacher", "old").access_token == TOKEN
    assert TOKEN not in path.read_text(encoding="utf-8")


def test_a_session_that_cannot_be_read_means_connect_again(sessions):
    path = sessions.session_path("teacher", "broken")
    path.write_text("enc:v1:not-a-real-token", encoding="utf-8")                # e.g. the key was replaced
    assert sessions.load_session("teacher", "broken") is None
    assert sessions.status_of("teacher", "broken")["logged_in"] is False


def test_a_renewed_token_is_saved_encrypted(sessions):
    sessions.save_session("teacher", "t2", _session())
    client = sessions.portal_for("teacher", "t2")
    client.session.access_token = "renewed-made-up-token"
    client.on_refresh(client.session)
    raw = sessions.session_path("teacher", "t2").read_text(encoding="utf-8")
    assert "renewed-made-up-token" not in raw and sessions.load_session("teacher", "t2").access_token == "renewed-made-up-token"


def test_uploaded_workbooks_are_deleted_after_the_kept_days(sessions, monkeypatch):
    from backend import config
    folder = sessions.session_dir("teacher", "t3")
    old, new, roster = folder / "uploaded_old.xlsx", folder / "uploaded_new.xlsx", folder / "roster_preparatory.json"
    backups = folder / "backups"
    backups.mkdir()
    old_backup = backups / "20260101_000000_uploaded_old.xlsx"
    for p in (old, new, roster, old_backup):
        p.write_bytes(b"x")
    month_ago = time.time() - 31 * 86400
    for p in (old, old_backup, roster):
        os.utime(p, (month_ago, month_ago))
    assert config.UPLOAD_KEEP_DAYS == 30
    assert sessions.prune_uploads() == 2
    assert not old.exists() and not old_backup.exists() and new.exists() and roster.exists()
    monkeypatch.setattr(config, "UPLOAD_KEEP_DAYS", 0)                           # 0: keep them
    os.utime(new, (month_ago, month_ago))
    assert sessions.prune_uploads() == 0 and new.exists()
