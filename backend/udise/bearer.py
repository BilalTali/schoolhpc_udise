"""
UDISE+ services that work with a token (Profile & Facilities, Teacher module), with the session the school's UDISE+
connection saved.

Both hand their web page an access token and a refresh token at the end of the sign-in. Requests carry
"Authorization: Bearer <access token>"; when it has expired (HTTP 401) the page asks api/auth/refresh-token for a new
pair. Every renewal returns a NEW refresh token and the old one stops working at once, so the new pair is saved
before anything else is done (udise_sessions.update_token). When the renewal is refused the session has ended:
the school presses 'Connect again'.
"""
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

from backend.udise import client

BASES = {"profile": "https://profile.udiseplus.gov.in/udiseplus",
         "teacher": "https://teacher.udiseplus.gov.in/teacher_module_backend"}
NAMES = {"profile": "School Profile", "teacher": "Teacher module"}
PACE = 0.5                          # seconds between calls: about 2 a second, gentle on UDISE+


class SessionEnded(client.UdiseError):
    """The saved session has ended: the school connects again (captcha, OTP)."""


class Refused(client.UdiseError):
    """UDISE+ answered but did not accept the request; .errors holds its field errors ({field, message})."""

    def __init__(self, message: str, status: int, errors=None):
        super().__init__(message)
        self.status, self.errors = status, errors or []


class Service:
    def __init__(self, school_id: str, service: str, saved: Dict[str, Any]):
        from backend.services import udise_sessions
        self._sessions = udise_sessions
        self.school_id, self.service, self.base = school_id, service, BASES[service]
        svc = (saved.get("services") or {}).get(service) or {}
        token = svc.get("token") or {}
        if not svc.get("connected") or not token.get("accessToken"):
            raise SessionEnded(f"The {NAMES[service]} is not connected. Press 'Connect UDISE+' on the UDISE+ card first.")
        self.token = dict(token)
        self.region_id = token.get("userRegionId")          # the school's id on this service
        self.http = client.new_http()
        self._next, self._lock = 0.0, threading.Lock()

    def _pace(self) -> None:
        with self._lock:
            wait = self._next - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next = time.monotonic() + PACE

    def _renew(self) -> None:
        try:
            resp = self.http.post(self.base + "/api/auth/refresh-token", json={"refreshToken": self.token.get("refreshToken")},
                                  timeout=client.TIMEOUT)
        except requests.RequestException as exc:
            raise client.UdiseError(f"UDISE+ did not answer ({type(exc).__name__}). Please try again in a few minutes.") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        fresh = body.get("data") if isinstance(body.get("data"), dict) else body
        if resp.ok and isinstance(fresh, dict) and fresh.get("accessToken"):
            self.token.update({k: v for k, v in fresh.items() if v})
            self._sessions.update_token(self.school_id, self.service, fresh)       # at once: the old pair is now dead
            return
        why = "the saved session has ended"
        self._sessions.mark_ended(self.school_id, self.service, why)
        raise SessionEnded(f"The {NAMES[self.service]} session has ended. Press 'Connect again' on the UDISE+ card, "
                           "then try again.")

    def _send(self, method: str, path: str, body: Any = None, params: Optional[Dict[str, Any]] = None,
              retry_slow: bool = True) -> Tuple[int, Any]:
        """One request: (HTTP status, answer as JSON or None). An expired token is renewed once; a slow read is
        asked again once (a save never is: it may have gone through)."""
        renewed = False
        for attempt in (1, 2, 3):
            self._pace()
            headers = {"Accept": "application/json", "Authorization": "Bearer " + str(self.token.get("accessToken"))}
            try:
                resp = self.http.request(method, self.base + path, json=body, params=params, headers=headers,
                                         timeout=(10, 120 if method != "GET" else 60), allow_redirects=False)
            except requests.RequestException as exc:
                if method == "GET" and retry_slow and attempt == 1:
                    time.sleep(5)
                    continue
                what = "the save" if method != "GET" else "the request"
                raise client.UdiseError(f"UDISE+ did not answer {what} ({type(exc).__name__})."
                                        + (" Check on the UDISE+ website whether it was saved before trying again."
                                           if method != "GET" else " Please try again later.")) from exc
            if resp.status_code == 401 and not renewed:
                self._renew()
                renewed = True
                continue
            if resp.status_code == 401:
                raise SessionEnded(f"The {NAMES[self.service]} session has ended. Press 'Connect again' on the UDISE+ card.")
            if resp.status_code >= 500 and method == "GET" and attempt == 1:
                time.sleep(5)
                continue
            if resp.status_code == 204 or not resp.content:
                return resp.status_code, None
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, None
        raise client.UdiseError("UDISE+ did not answer. Please try again later.")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        status, answer = self._send("GET", path, params=params)
        if status >= 400:
            raise Refused(refusal(answer, status), status, field_errors(answer))
        return answer

    def post(self, path: str, body: Any, method: str = "POST") -> Any:
        """A save, sent once. A refusal is Refused with UDISE+'s own reasons."""
        status, answer = self._send(method, path, body=body, retry_slow=False)
        if status >= 400 or (isinstance(answer, dict) and str(answer.get("status")).upper() in ("ERROR", "FALSE")):
            raise Refused(refusal(answer, status), status, field_errors(answer))
        return answer


def field_errors(answer: Any) -> list:
    """UDISE+'s field errors: [{"field", "message"}]. They come as a list of {fieldName, errorDescription}."""
    items = answer if isinstance(answer, list) else (answer or {}).get("errors") if isinstance(answer, dict) else None
    out = []
    for e in items or []:
        if isinstance(e, dict):
            out.append({"field": e.get("fieldName") or e.get("field") or "",
                        "message": str(e.get("errorDescription") or e.get("message") or e)})
        else:
            out.append({"field": "", "message": str(e)})
    return out


def refusal(answer: Any, status: int) -> str:
    errors = field_errors(answer)
    if errors:
        return "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors)
    if isinstance(answer, dict) and answer.get("message"):
        return str(answer["message"])
    if status == 412:
        return "UDISE+ asks for an earlier form to be completed first."
    if status == 403:
        return "UDISE+ refused: this account may not change this data now (the data entry may be closed or locked)."
    return f"UDISE+ answered HTTP {status}."
