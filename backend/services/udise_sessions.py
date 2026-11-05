"""
A school's UDISE+ connection: one sign-in, a saved session for each of the four services.

connect()        username + password -> UDISE+'s captcha picture (the person reads it)
verify_captcha() the typed answer -> signed in, or an OTP to type (verify_otp())
                 once signed in, every service is opened and what it hands back is saved
status()         what is saved, per service (no secrets)
Saved at data/sessions/school_<id>/udise.json, encrypted with the app key (it holds the password and the
sessions). Diagnostics of the last sign-in - addresses and names only, never values - in udise_trail.json.
"""
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.services import secrets_box
from backend.services.hpc_sessions import session_dir
from backend.udise import client

PENDING: Dict[str, Dict[str, Any]] = {}          # school id -> sign-in in progress (connection, form, details)
PENDING_TTL = 10 * 60
MAX_FAILED, FAILED_WINDOW = 3, 15 * 60          # wrong sign-ins allowed, and over how long (protects the account)
FAILED: Dict[str, list] = {}


def _file(school_id: str):
    return session_dir("school", school_id) / "udise.json"


def _trail_file(school_id: str):
    return session_dir("school", school_id) / "udise_trail.json"


def _load(school_id: str) -> Dict[str, Any]:
    path = _file(school_id)
    if not path.exists():
        return {}
    try:
        return json.loads(secrets_box.decrypt(path.read_text(encoding="utf-8")))
    except Exception:                                 # the key was replaced: counts as not connected
        return {}


def _save(school_id: str, data: Dict[str, Any]) -> None:
    path = _file(school_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(secrets_box.encrypt(json.dumps(data)), encoding="utf-8")
    tmp.replace(path)
    for key in [k for k in list(_LIVE) if k[0] == school_id]:     # the sign-in changed: check the services afresh
        _LIVE.pop(key, None)


def _keep_trail(school_id: str, steps: List[Dict[str, Any]], services: Dict[str, List[Dict[str, Any]]] = None) -> None:
    _trail_file(school_id).write_text(json.dumps({"at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                                  "sign_in": steps, "services": services or {}}, indent=1), encoding="utf-8")


_TOKEN_LOCK = threading.Lock()


def load_saved(school_id: str) -> Dict[str, Any]:
    """The saved connection (sessions and tokens of every service). Empty when not connected."""
    return _load(school_id)


def update_token(school_id: str, service: str, fresh: Dict[str, Any]) -> None:
    """Keeps a service's renewed tokens. Profile and Teacher hand out a NEW refresh token with every renewal and
    the old one stops working at once, so a renewal that is not kept ends the session: this must run every time."""
    with _TOKEN_LOCK:
        data = _load(school_id)
        svc = (data.get("services") or {}).get(service)
        if not svc or not isinstance(svc.get("token"), dict):
            return
        for name in ("accessToken", "refreshToken", "expiresIn", "refreshTokenExpiresIn", "timeCreated",
                     "refreshTokenTimeCreated"):
            if fresh.get(name):
                svc["token"][name] = fresh[name]
        _save(school_id, data)


def mark_ended(school_id: str, service: str, why: str) -> None:
    """A service's session can no longer be renewed: shown as not connected until 'Connect again'."""
    with _TOKEN_LOCK:
        data = _load(school_id)
        svc = (data.get("services") or {}).get(service)
        if svc:
            svc.update(connected=False, why=why)
            _save(school_id, data)


def _blocked(school_id: str) -> str:
    now = time.time()
    FAILED[school_id] = [t for t in FAILED.get(school_id, []) if now - t < FAILED_WINDOW]
    if len(FAILED[school_id]) < MAX_FAILED:
        return ""
    wait = int((min(FAILED[school_id]) + FAILED_WINDOW - now) // 60) + 1
    return (f"Connecting was stopped after {MAX_FAILED} failed attempts, to protect the UDISE+ account. Check the "
            f"username and password on the UDISE+ website, then try again in {wait} minute(s).")


def _failed(school_id: str) -> str:
    FAILED.setdefault(school_id, []).append(time.time())
    stop = _blocked(school_id)
    if stop:
        PENDING.pop(school_id, None)
    return stop


LIVE_TTL = 90                                    # seconds a live check of a service is trusted
_LIVE: Dict[Tuple[str, str], Tuple[float, Optional[bool], str]] = {}


def _probe(school_id: str, key: str, saved: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    """One small read on a service: (True, ""), (False, why) when UDISE+ says the session ended - marked ended - or
    (None, why) when it could not be checked (UDISE+ did not answer; DCF has no read the app can use)."""
    from backend.udise import bearer
    from backend.udise import sdms as sdms_client
    try:
        if key == "sdms":
            sdms_client.Sdms(saved).school_id()
        elif key == "profile":
            svc = bearer.Service(school_id, "profile", saved)
            svc.get(f"/school/{svc.region_id}")
        elif key == "teacher":
            svc = bearer.Service(school_id, "teacher", saved)
            state = svc.token.get("userStateId")
            if not state:
                return None, "not checked"
            svc.get(f"/teacher/dropdown/all/1/{state}")
        else:
            return None, "not checked"
        return True, ""
    except (sdms_client.SessionEnded, bearer.SessionEnded) as exc:
        mark_ended(school_id, key, str(exc))
        return False, str(exc)
    except Exception as exc:                        # UDISE+ did not answer, refused the read ...
        return None, str(exc)


def status(school_id: str, check: bool = False) -> Dict[str, Any]:
    """The four services; with check, each connected one is asked now (a saved sign-in alone is not proof)."""
    data = _load(school_id)
    services = data.get("services") or {}
    live: Dict[str, Tuple[Optional[bool], str]] = {}
    if check:
        todo = []
        for key in client.SERVICES:
            if not (services.get(key) or {}).get("connected"):
                continue
            hit = _LIVE.get((school_id, key))
            if hit and time.time() - hit[0] < LIVE_TTL:
                live[key] = (hit[1], hit[2])
            else:
                todo.append(key)
        if todo:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as pool:
                for key, result in zip(todo, pool.map(lambda k: _probe(school_id, k, data), todo)):
                    _LIVE[(school_id, key)] = (time.time(), *result)
                    live[key] = result
        data = _load(school_id)                      # a probe may have marked a service ended
        services = data.get("services") or {}
    rows = []
    for key, svc in client.SERVICES.items():
        connected = bool((services.get(key) or {}).get("connected"))
        ok, why = live.get(key, (None, ""))
        rows.append({"key": key, "name": svc["name"], "connected": connected and ok is not False,
                     "checked": connected and ok is True, "why": (services.get(key) or {}).get("why", "") or
                     (f"Could not check just now: {why}" if connected and ok is None and why and why != "not checked" else "")})
    return {"connected": any(r["connected"] for r in rows), "username": data.get("username", ""),
            "connected_at": data.get("connected_at"), "services": rows}


def _captcha_step(school_id: str, username: str, password: str, error: str = "") -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    try:
        http, form, image = client.begin(steps)
    except client.UdiseError as exc:
        _keep_trail(school_id, steps)
        return {"success": False, "error": str(exc)}
    PENDING[school_id] = {"http": http, "form": form, "username": username, "password": password,
                          "steps": steps, "at": time.time()}
    return {"success": not error, "status": "captcha_required", "captcha_image": client.picture(image),
            **({"error": error} if error else {"message": "Type the 6 characters shown in the picture."})}


def connect(school_id: str, username: str, password: str) -> Dict[str, Any]:
    stop = _blocked(school_id)
    if stop:
        return {"success": False, "error": stop}
    sign_out_remote(school_id)                       # an old SDMS session still active there blocks the new sign-in
    username = (username or "").strip()
    if not username or not password:
        saved = _load(school_id)
        username, password = username or saved.get("username", ""), password or saved.get("password", "")
    if not username or not password:
        return {"success": False, "error": "Type the UDISE+ username and password."}
    return _captcha_step(school_id, username, password)


def new_captcha(school_id: str) -> Dict[str, Any]:
    pending = PENDING.get(school_id)
    if not pending or time.time() - pending["at"] > PENDING_TTL:
        return {"success": False, "error": "The sign-in timed out. Press Connect again."}
    return _captcha_step(school_id, pending["username"], pending["password"])


def verify_captcha(school_id: str, answer: str) -> Dict[str, Any]:
    stop = _blocked(school_id)
    if stop:
        return {"success": False, "error": stop}
    pending = PENDING.get(school_id)
    if not pending or time.time() - pending["at"] > PENDING_TTL:
        PENDING.pop(school_id, None)
        return {"success": False, "error": "The sign-in timed out. Press Connect again."}
    if len(str(answer or "").strip()) != 6:
        return {"success": False, "status": "captcha_required", "error": "The captcha has 6 characters."}
    steps = pending["steps"]
    try:
        result = client.submit(pending["http"], pending["form"], pending["username"], pending["password"], answer, steps)
    except client.UdiseError as exc:
        _keep_trail(school_id, steps)
        return {"success": False, "error": str(exc)}
    return _after_step(school_id, pending, result)


def verify_otp(school_id: str, otp: str) -> Dict[str, Any]:
    stop = _blocked(school_id)
    if stop:
        return {"success": False, "error": stop}
    pending = PENDING.get(school_id)
    if not pending or not pending.get("otp_form") or time.time() - pending["at"] > PENDING_TTL:
        return {"success": False, "error": "The sign-in timed out. Press Connect again."}
    if not str(otp or "").strip():
        return {"success": False, "status": "otp_required", "error": "Type the OTP."}
    steps = pending["steps"]
    try:
        result = client.submit_otp(pending["http"], pending["otp_form"], otp, steps)
    except client.UdiseError as exc:
        _keep_trail(school_id, steps)
        return {"success": False, "error": str(exc)}
    return _after_step(school_id, pending, result)


def _after_step(school_id: str, pending: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    steps = pending["steps"]
    if result["status"] == "otp_required":
        pending.update(otp_form=result["form"], at=time.time())
        _keep_trail(school_id, steps)
        return {"success": True, "status": "otp_required",
                "message": "UDISE+ sent an OTP to the registered mobile number. Type it here."}
    if result["status"] == "refused":
        _keep_trail(school_id, steps)
        if result.get("captcha_wrong"):                  # a misread picture is not a wrong password
            return _captcha_step(school_id, pending["username"], pending["password"],
                                 error="That captcha answer was not right. Please try this new picture.")
        stop = _failed(school_id)
        PENDING.pop(school_id, None)
        return {"success": False, "error": stop or result["error"]}
    # signed in: open every service with this connection and keep what each hands back
    found, trails = client.open_services(pending["http"])
    _keep_trail(school_id, steps, trails)
    PENDING.pop(school_id, None)
    FAILED.pop(school_id, None)
    _save(school_id, {"username": pending["username"], "password": pending["password"],
                      "connected_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                      "auth_cookies": {c.name: c.value for c in pending["http"].cookies
                                       if c.domain.lstrip(".").endswith("auth.udiseplus.gov.in")},
                      "services": found})
    from backend.services import audit
    audit.record(f"school_admin:{school_id}", "connect_udise", "settings", school_id, None,
                 {"services": {k: bool(v.get("connected")) for k, v in found.items()}})
    return {"success": True, "status": "authenticated", **status(school_id)}


def sdms_not_connected(school_id: str) -> str:
    """Why SDMS cannot be used now, in words the school can act on (the saved reason from the last Connect)."""
    saved = _load(school_id)
    sdms = (saved.get("services") or {}).get("sdms") or {}
    when = str(saved.get("connected_at") or "")[11:16]
    if sdms.get("why"):
        reason = sdms["why"].split(" - ")[0].replace("Student module (SDMS) ", "SDMS ")
        return (f"SDMS is not connected: at the last Connect{f' ({when} UTC)' if when else ''} {reason}. The other UDISE+ "
                "services can still show connected. Press Connect again on the UDISE+ card; if SDMS refuses again, its "
                "previous session is still open there - wait 15-30 minutes, then connect again.")
    return "SDMS is not connected. Press 'Connect UDISE+' on the Home page first."


def sign_out_remote(school_id: str) -> None:
    """Signs the saved SDMS session out on SDMS's own server (best effort, never raises). SDMS keeps one session per
    account: one only forgotten here stays active there and makes the next sign-in fail (oauthError=auth_failed)."""
    import requests
    saved = _load(school_id)
    sdms = (saved.get("services") or {}).get("sdms") or {}
    cookies = sdms.get("cookies") or {}
    if not cookies:
        return
    http = requests.Session()
    for name, value in cookies.items():
        http.cookies.set(name, value, domain="sdms.udiseplus.gov.in")
    headers = {"X-XSRF-TOKEN": cookies.get("XSRF-TOKEN", "")}
    for method in ("POST", "GET"):
        try:
            http.request(method, "https://sdms.udiseplus.gov.in/p0/logout", headers=headers, timeout=(10, 20),
                         allow_redirects=False)
            break
        except Exception:
            continue


def disconnect(school_id: str) -> Dict[str, Any]:
    """Signs the SDMS session out on SDMS, then forgets the sessions and the saved password."""
    sign_out_remote(school_id)
    PENDING.pop(school_id, None)
    for path in (_file(school_id), _trail_file(school_id)):
        if path.exists():
            path.unlink()
    return {"success": True, **status(school_id)}
