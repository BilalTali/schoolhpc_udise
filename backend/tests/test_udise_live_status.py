"""UDISE+ connection status is what each service says now, not the saved sign-in. UDISE+ is MOCKED here."""
import pytest


def test_udise_services_are_asked_and_an_ended_one_is_shown_ended(monkeypatch):
    from backend.services import udise_sessions
    from backend.udise import sdms as sdms_client
    saved = {"username": "u", "services": {k: {"connected": True} for k in ("dcf", "profile", "teacher", "sdms")}}
    ended = []
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: saved)
    monkeypatch.setattr(udise_sessions, "mark_ended", lambda sid, key, why: ended.append(key) or
                        saved["services"][key].update(connected=False, why=why))
    udise_sessions._LIVE.clear()

    def probe(school_id, key, data):
        if key == "sdms":
            udise_sessions.mark_ended(school_id, key, "The SDMS session has ended.")
            return False, "The SDMS session has ended."
        return (True, "") if key != "dcf" else (None, "not checked")
    monkeypatch.setattr(udise_sessions, "_probe", probe)
    st = {s["key"]: s for s in udise_sessions.status("s1", check=True)["services"]}
    assert st["sdms"]["connected"] is False and "has ended" in st["sdms"]["why"] and ended == ["sdms"]
    assert st["profile"]["connected"] and st["profile"]["checked"]
    assert st["dcf"]["connected"] and not st["dcf"]["checked"] and st["dcf"]["why"] == ""


def test_a_service_that_refuses_the_sign_in_is_not_connected(monkeypatch):
    """SDMS answering the hand-over with its login page (?oauthError=auth_failed) - e.g. the account is open in a
    browser - is shown as not connected with the reason, never as connected."""
    import requests
    from backend.udise import client
    landing = {"sdms": "https://sdms.udiseplus.gov.in/p0/v1/login?oauthError=auth_failed"}

    class Resp:
        status_code = 200

    def follow(http, method, url, trail):
        r = Resp()
        r.url = next((landing[k] for k, s in client.SERVICES.items() if s["start"] == url and k in landing),
                     f"https://{next(s['host'] for s in client.SERVICES.values() if s['start'] == url)}/home")
        return r
    monkeypatch.setattr(client, "follow", follow)
    monkeypatch.setattr(client, "final_url", lambda r: r.url)
    found, _ = client.open_services(requests.Session())
    assert found["sdms"]["connected"] is False and "refused the sign-in (auth_failed)" in found["sdms"]["why"]
    assert "sign out there" in found["sdms"]["why"]
    assert found["profile"]["connected"] is True


@pytest.mark.real_sign_out
def test_disconnect_signs_the_sdms_session_out_on_sdms_first(monkeypatch):
    """SDMS keeps one session per account: one only forgotten here would block the next sign-in (auth_failed)."""
    import requests
    from backend.services import udise_sessions
    sent = []
    monkeypatch.setattr(requests.Session, "request", lambda self, method, url, **kw: sent.append(
        (method, url, dict(self.cookies), kw.get("headers"))) or type("R", (), {"status_code": 302})())
    monkeypatch.setattr(udise_sessions, "_load", lambda sid: {"services": {"sdms": {"cookies": {
        "JSESSIONID": "made-up", "XSRF-TOKEN": "x1"}}}})
    udise_sessions.sign_out_remote("s1")
    method, url, cookies, headers = sent[0]
    assert method == "POST" and url == "https://sdms.udiseplus.gov.in/p0/logout"
    assert cookies["JSESSIONID"] == "made-up" and headers["X-XSRF-TOKEN"] == "x1"
