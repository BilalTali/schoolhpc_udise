"""
HPC portal sessions for schools and teachers.

Each school/teacher has its own portal session saved at data/sessions/<kind>_<id>/session.json.
Logging in: start() reads PARAKH's captcha and returns the picture; the person types the answer
and verify_captcha() logs in (then verify_otp() if the portal asks for an OTP). The connection the
captcha came from is kept for a few minutes, because PARAKH ties the answer to it.
With HPC_AUTO_CAPTCHA (unsupported) the app reads the captcha itself instead.
"""
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from backend.config import AUTO_CAPTCHA, SESSIONS_DIR
from backend.hpc import portal

PENDING_OTP: Dict[str, Dict[str, Any]] = {}     # "<kind>_<id>" -> pending login
PENDING_CAPTCHA: Dict[str, Dict[str, Any]] = {}  # "<kind>_<id>" -> connection, captcha_id, login details
CAPTCHA_TTL = 10 * 60


def session_dir(kind: str, entity_id: str) -> Path:
    d = SESSIONS_DIR / f"{kind}_{entity_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_path(kind: str, entity_id: str) -> Path:
    return session_dir(kind, entity_id) / "session.json"


def status_of(kind: str, entity_id: str) -> Dict[str, Any]:
    sess = portal.Session.load(session_path(kind, entity_id))
    mode = "automatic (unsupported)" if AUTO_CAPTCHA else "typed"
    if not sess:
        return {"logged_in": False, "reason": "No HPC session yet. Click 'Start Session'.", "captcha_mode": mode}
    return {"logged_in": True, "user": sess.name, "school": sess.school_name, "role": sess.role, "captcha_mode": mode}


def start(kind: str, entity_id: str, login_id: str, password: str) -> Dict[str, Any]:
    """Begins a login: returns PARAKH's captcha picture for the person to answer (the default),
    or logs in straight away when the unsupported automatic captcha is switched on."""
    if not AUTO_CAPTCHA:
        return _new_captcha(kind, entity_id, login_id, password)
    try:
        sess = portal.login(login_id, password)
    except portal.OtpRequired as exc:
        PENDING_OTP[f"{kind}_{entity_id}"] = {**exc.pending, "at": time.time()}
        return {"success": True, "status": "otp_required",
                "message": "The portal sent an OTP to your registered mobile number."}
    except portal.PortalError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Could not reach the HPC portal: {exc}"}
    return _saved(kind, entity_id, sess)


def _new_captcha(kind: str, entity_id: str, login_id: str, password: str, error: str = "") -> Dict[str, Any]:
    try:
        http, captcha_id, image = portal.begin_login()
    except portal.PortalError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Could not reach the HPC portal: {exc}"}
    PENDING_CAPTCHA[f"{kind}_{entity_id}"] = {"http": http, "captcha_id": captcha_id, "login_id": login_id,
                                             "password": password, "at": time.time()}
    image = image if image.startswith("data:") else f"data:image/png;base64,{image}"
    return {"success": not error, "status": "captcha_required", "captcha_image": image,
            **({"error": error} if error else {"message": "Type the answer shown in the picture."})}


def new_captcha(kind: str, entity_id: str) -> Dict[str, Any]:
    """Another picture for the login in progress (the old one may be hard to read)."""
    pending = PENDING_CAPTCHA.get(f"{kind}_{entity_id}")
    if not pending or time.time() - pending["at"] > CAPTCHA_TTL:
        return {"success": False, "error": "The login timed out. Please click Connect again."}
    return _new_captcha(kind, entity_id, pending["login_id"], pending["password"])


def verify_captcha(kind: str, entity_id: str, answer: str) -> Dict[str, Any]:
    """Logs in with the answer the person typed. A wrong answer comes back with a fresh picture."""
    key = f"{kind}_{entity_id}"
    pending = PENDING_CAPTCHA.get(key)
    if not pending or time.time() - pending["at"] > CAPTCHA_TTL:
        PENDING_CAPTCHA.pop(key, None)
        return {"success": False, "error": "The login timed out. Please click Connect again."}
    if not str(answer or "").strip():
        return {"success": False, "status": "captcha_required", "error": "Type the answer shown in the picture."}
    try:
        token = portal.answer_captcha(pending["http"], pending["captcha_id"], answer)
    except portal.PortalError:
        return _new_captcha(kind, entity_id, pending["login_id"], pending["password"],
                            error="That answer was not accepted. Please try this new picture.")
    except Exception as exc:
        return {"success": False, "error": f"Could not reach the HPC portal: {exc}"}
    PENDING_CAPTCHA.pop(key, None)
    try:
        sess = portal.login_with_token(pending["http"], pending["login_id"], pending["password"], token)
    except portal.OtpRequired as exc:
        PENDING_OTP[key] = {**exc.pending, "at": time.time()}
        return {"success": True, "status": "otp_required",
                "message": "The portal sent an OTP to your registered mobile number."}
    except portal.PortalError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Could not reach the HPC portal: {exc}"}
    return _saved(kind, entity_id, sess)


def verify_otp(kind: str, entity_id: str, otp: str) -> Dict[str, Any]:
    pending = PENDING_OTP.get(f"{kind}_{entity_id}")
    if not pending or time.time() - pending["at"] > 600:
        return {"success": False, "error": "Login timed out. Please start the HPC session again."}
    try:
        sess = portal.verify_otp(pending, otp)
    except portal.PortalError as exc:
        return {"success": False, "error": str(exc)}
    PENDING_OTP.pop(f"{kind}_{entity_id}", None)
    return _saved(kind, entity_id, sess)


def end(kind: str, entity_id: str) -> Dict[str, Any]:
    path = session_path(kind, entity_id)
    if path.exists():
        path.unlink()
    return {"success": True, "message": "HPC session ended."}


def _saved(kind: str, entity_id: str, sess: portal.Session) -> Dict[str, Any]:
    sess.save(session_path(kind, entity_id))
    from backend.services import audit
    audit.record(f"{'teacher' if kind == 'teacher' else 'school_admin'}:{entity_id}", "connect_parakh", "settings",
                 entity_id, None, {"portal_user": sess.name})
    return {"success": True, "status": "authenticated", "user": sess.name,
            "school": sess.school_name, "role": sess.role}


def portal_for(kind: str, entity_id: str, login_id: Optional[str] = None,
               password: Optional[str] = None) -> portal.Portal:
    """
    An API client for this school/teacher. Renewed tokens are saved automatically. If the
    session cannot be renewed and saved credentials are given, it logs in again once.
    """
    path = session_path(kind, entity_id)
    sess = portal.Session.load(path)
    if not sess and login_id and password and AUTO_CAPTCHA:      # unsupported: logs in by itself
        result = start(kind, entity_id, login_id, password)
        if result.get("status") == "authenticated":
            sess = portal.Session.load(path)
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "PARAKH HPC session is not active. Click 'Start HPC Session' first.")
    client = portal.Portal(sess, on_refresh=lambda s: s.save(path))
    if login_id and password and AUTO_CAPTCHA:
        client.relogin = lambda: portal.login(login_id, password)
    return client
