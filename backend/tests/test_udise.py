"""UDISE+ connection: the sign-in steps (captcha the person types, OTP), the saved sessions (encrypted), and the
diagnostics (names only). A fake UDISE+ - nothing here reaches the real one."""
import base64
import json

import pytest
import requests

from backend.services import hpc_sessions, udise_sessions
from backend.udise import client


def page(url, html, status=200):
    resp = requests.Response()
    resp.status_code, resp.url, resp._content = status, url, html.encode()
    resp.headers["Content-Type"] = "text/html;charset=UTF-8"
    return resp


LOGIN_FORM = """<html><title>UDISE+ Login</title><form action="/login" method="post">
<input type="hidden" name="_csrf" value="c1"><input type="hidden" name="loginTxnId" value="t1">
<input name="username"><input name="password" type="password">
<input type="radio" name="captchaMode" value="image" checked><input type="radio" name="captchaMode" value="audio">
<input name="captcha"></form></html>"""
OTP_FORM = """<html><title>Verify OTP</title><form action="/verify-otp" method="post">
<input type="hidden" name="_csrf" value="c2"><input name="otp"></form></html>"""


def test_the_sign_in_page_and_where_a_step_ended():
    form = next(f for f in client._forms(LOGIN_FORM).forms)
    assert form["action"] == "/login" and form["inputs"]["_csrf"] == "c1" and form["inputs"]["captchaMode"] == "image"
    trail = []
    assert client._outcome(page("https://auth.udiseplus.gov.in/verify", OTP_FORM), trail)["status"] == "otp_required"
    wrong = client._outcome(page("https://auth.udiseplus.gov.in/login?captchaError&loginTxnId=t1", LOGIN_FORM), trail)
    assert wrong["status"] == "refused" and wrong["captcha_wrong"]
    refused = client._outcome(page("https://auth.udiseplus.gov.in/login?error&loginTxnId=t1", LOGIN_FORM), trail)
    assert refused["status"] == "refused" and not refused["captcha_wrong"] and "password" in refused["error"]
    assert client._outcome(page("https://sdms.udiseplus.gov.in/p0/home", "<html></html>"), trail)["status"] == "signed_in"
    assert "t1" not in json.dumps(trail)                                    # names only, never values


def test_the_web_apps_session_handed_at_the_end_of_the_redirects():
    blob = base64.b64encode(json.dumps({"token": "x", "refreshToken": "y"}).encode()).decode().rstrip("=")
    assert client._handed_token(f"https://profile.udiseplus.gov.in/#/auth-redirection?code={blob}") == {"token": "x", "refreshToken": "y"}
    assert client._handed_token("https://profile.udiseplus.gov.in/#/home") is None
    shape = client._shape(f"https://profile.udiseplus.gov.in/#/auth-redirection?code={blob}")
    assert shape["fragment_query"] == ["code"] and blob not in json.dumps(shape)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path)
    udise_sessions.PENDING.clear()
    udise_sessions.FAILED.clear()
    state = {"answers": [], "otp": None}

    def begin(trail):
        trail.append({"host": "auth.udiseplus.gov.in", "path": "/login"})
        return requests.Session(), {"action": "/login", "method": "post", "inputs": {"_csrf": "c"}, "page": client.AUTH + "/login"}, b"\x89PNGpic"

    def submit(http, form, username, password, answer, trail):
        state["answers"].append(answer)
        if answer == "WRONG1":
            return {"status": "refused", "error": "The captcha answer was not right.", "captcha_wrong": True}
        if password != "right-pass":
            return {"status": "refused", "error": "UDISE+ did not accept the username or password.", "captcha_wrong": False}
        return {"status": "otp_required", "form": {"action": "/otp", "method": "post", "inputs": {"otp": ""}, "page": client.AUTH}}

    def submit_otp(http, form, otp, trail):
        state["otp"] = otp
        return {"status": "signed_in"} if otp == "123456" else {"status": "refused", "error": "Wrong OTP", "captcha_wrong": False}

    def open_services(http):
        found = {k: {"connected": k == "sdms", "token": None, "cookies": {"SESSION": "secret-cookie"} if k == "sdms" else {},
                     "landed": "", "why": "" if k == "sdms" else "UDISE+ asked to sign in again for this service"}
                 for k in client.SERVICES}
        return found, {k: [{"note": "result"}] for k in client.SERVICES}

    monkeypatch.setattr(client, "begin", begin)
    monkeypatch.setattr(client, "submit", submit)
    monkeypatch.setattr(client, "submit_otp", submit_otp)
    monkeypatch.setattr(client, "open_services", open_services)
    return state, tmp_path


def test_connecting_with_captcha_then_otp_saves_each_services_session_encrypted(fake):
    state, folder = fake
    first = udise_sessions.connect("s1", "school01", "right-pass")
    assert first["status"] == "captcha_required" and first["captcha_image"].startswith("data:image/png;base64,")
    again = udise_sessions.verify_captcha("s1", "WRONG1")                  # a misread picture: a new one, no penalty
    assert again["status"] == "captcha_required" and "not right" in again["error"] and not udise_sessions.FAILED.get("s1")
    assert udise_sessions.verify_captcha("s1", "AB12CD")["status"] == "otp_required"
    done = udise_sessions.verify_otp("s1", "123456")
    assert done["status"] == "authenticated" and done["connected"] and done["username"] == "school01"
    by = {s["key"]: s for s in done["services"]}
    assert by["sdms"]["connected"] and not by["profile"]["connected"] and by["profile"]["why"]
    saved = (folder / "school_s1" / "udise.json").read_text(encoding="utf-8")
    assert "right-pass" not in saved and "secret-cookie" not in saved     # encrypted on disk
    assert "secret" not in json.dumps(udise_sessions.status("s1"))        # the status shows no secrets
    assert udise_sessions.connect("s1", "", "")["status"] == "captcha_required"   # the saved login is used again


def test_wrong_passwords_stop_after_three_to_protect_the_account(fake):
    for _ in range(3):
        assert udise_sessions.connect("s2", "school02", "bad")["status"] == "captcha_required"
        result = udise_sessions.verify_captcha("s2", "AB12CD")
        assert result["success"] is False
    assert "stopped after 3 failed attempts" in result["error"]
    assert "stopped" in udise_sessions.connect("s2", "school02", "right-pass")["error"]


def test_disconnecting_forgets_the_sessions_and_the_password(fake):
    state, folder = fake
    udise_sessions.connect("s3", "school03", "right-pass")
    udise_sessions.verify_captcha("s3", "AB12CD")
    udise_sessions.verify_otp("s3", "123456")
    assert udise_sessions.status("s3")["connected"]
    udise_sessions.disconnect("s3")
    assert not udise_sessions.status("s3")["connected"] and not (folder / "school_s3" / "udise.json").exists()
