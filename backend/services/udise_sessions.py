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
import time
from datetime import datetime
from typing import Any, Dict, List

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


def _keep_trail(school_id: str, steps: List[Dict[str, Any]], services: Dict[str, List[Dict[str, Any]]] = None) -> None:
    _trail_file(school_id).write_text(json.dumps({"at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                                  "sign_in": steps, "services": services or {}}, indent=1), encoding="utf-8")


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


def status(school_id: str) -> Dict[str, Any]:
    data = _load(school_id)
    services = data.get("services") or {}
    return {"connected": any(s.get("connected") for s in services.values()), "username": data.get("username", ""),
            "connected_at": data.get("connected_at"),
            "services": [{"key": key, "name": svc["name"], "connected": bool((services.get(key) or {}).get("connected")),
                          "why": (services.get(key) or {}).get("why", "")}
                         for key, svc in client.SERVICES.items()]}


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


def disconnect(school_id: str) -> Dict[str, Any]:
    """Forgets the sessions and the saved password."""
    PENDING.pop(school_id, None)
    for path in (_file(school_id), _trail_file(school_id)):
        if path.exists():
            path.unlink()
    return {"success": True, **status(school_id)}
