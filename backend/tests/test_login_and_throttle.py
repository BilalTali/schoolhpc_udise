"""Teacher-typed captcha login (fake PARAKH) and request throttling. No network."""
import threading

import pytest
from fastapi import HTTPException

from backend.hpc import portal
from backend.services import hpc_sessions


@pytest.fixture
def fake_parakh(monkeypatch, tmp_path):
    """begin/answer/login replaced; the captcha answer is always 11, the second login needs an OTP."""
    state = {"issued": 0, "logins": [], "need_otp": False}

    def begin():
        state["issued"] += 1
        return object(), f"cap{state['issued']}", "iVBORw0KGgo="        # PNG header bytes, base64

    def answer(http, captcha_id, value):
        if value.strip() != "11":
            raise portal.PortalError("The captcha answer was not accepted.")
        return f"token-{captcha_id}"

    def login(http, login_id, password, token):
        state["logins"].append((login_id, password, token))
        if state["need_otp"]:
            raise portal.OtpRequired({"staff_id": login_id, "login_data": {"temp_token": "t"}})
        return portal.Session(access_token="A", refresh_token="R", staff={"name": "Test Teacher"})

    monkeypatch.setattr(portal, "begin_login", begin)
    monkeypatch.setattr(portal, "answer_captcha", answer)
    monkeypatch.setattr(portal, "login_with_token", login)
    monkeypatch.setattr(portal, "login", lambda *a: pytest.fail("automatic captcha must not be used"))
    monkeypatch.setattr(hpc_sessions, "AUTO_CAPTCHA", False)
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(hpc_sessions, "session_dir", lambda kind, i: tmp_path / f"{kind}_{i}")
    hpc_sessions.PENDING_CAPTCHA.clear()
    return state


def test_start_shows_the_captcha_and_a_wrong_answer_gets_a_new_picture(fake_parakh):
    first = hpc_sessions.start("teacher", "t1", "T7AFCD2", "secret")
    assert first["status"] == "captcha_required" and first["captcha_image"].startswith("data:image/png;base64,")
    assert fake_parakh["logins"] == []                                    # nothing sent before the answer

    wrong = hpc_sessions.verify_captcha("teacher", "t1", "12")
    assert wrong["status"] == "captcha_required" and "not accepted" in wrong["error"] and fake_parakh["issued"] == 2

    ok = hpc_sessions.verify_captcha("teacher", "t1", " 11 ")
    assert ok["status"] == "authenticated" and fake_parakh["logins"] == [("T7AFCD2", "secret", "token-cap2")]
    assert hpc_sessions.status_of("teacher", "t1")["logged_in"] is True
    assert hpc_sessions.status_of("teacher", "t1")["captcha_mode"] == "typed"


def test_otp_after_the_captcha(fake_parakh):
    fake_parakh["need_otp"] = True
    hpc_sessions.start("teacher", "t2", "ID", "pw")
    result = hpc_sessions.verify_captcha("teacher", "t2", "11")
    assert result["status"] == "otp_required" and "t" in str(hpc_sessions.PENDING_OTP.get("teacher_t2"))


def test_new_picture_and_timeout(fake_parakh, monkeypatch):
    assert hpc_sessions.new_captcha("teacher", "nobody")["success"] is False
    hpc_sessions.start("teacher", "t3", "ID", "pw")
    assert hpc_sessions.new_captcha("teacher", "t3")["status"] == "captcha_required"
    hpc_sessions.PENDING_CAPTCHA["teacher_t3"]["at"] -= hpc_sessions.CAPTCHA_TTL + 1
    late = hpc_sessions.verify_captcha("teacher", "t3", "11")
    assert late["success"] is False and "timed out" in late["error"]


def test_no_silent_relogin_when_the_session_is_gone(fake_parakh):
    with pytest.raises(HTTPException) as exc:
        hpc_sessions.portal_for("teacher", "t4", "ID", "pw")
    assert exc.value.status_code == 401 and fake_parakh["issued"] == 0 and fake_parakh["logins"] == []


def test_requests_are_spaced_out_across_threads(monkeypatch):
    waits = []
    monkeypatch.setattr(portal.time, "sleep", lambda s: waits.append(s))
    client = portal.Portal(portal.Session(access_token="x", staff={}))
    client.min_interval = 0.25                                  # 4 a second
    threads = [threading.Thread(target=client._pace) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # eight requests at once: each waits for its turn, the last one about 7 x 0.25 s
    assert len(waits) >= 7 and max(waits) == pytest.approx(1.75, abs=0.1)
