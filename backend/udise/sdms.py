"""
SDMS (UDISE+ Student module): reading the school's students for the current session, with the session the school's
UDISE+ connection saved. Read only - nothing here writes to SDMS.

The calls are the ones SDMS's own pages make for the current session ("cy"):
  api/user                                   the signed-in school (userRegionId = SDMS school id)
  api/cy/school/{school}                     the school: classes, session dates, yearId
  api/v2/school/total-enr/class-wise/{school} the dashboard: each class with its enrolment
  api/cy/students/all/{school}               every student's general profile, all classes
  api/v2/students/enrolment/{student}        the student form's Enrolment part
  api/v2/students/facility/{student}         the student form's Facility part
"""
import threading
import time
from typing import Any, Dict, Optional

import requests

from backend.udise import client

BASE = "https://sdms.udiseplus.gov.in/p0/"
PACE = 0.5                          # seconds between calls: about 2 a second, gentle on UDISE+


class SessionEnded(client.UdiseError):
    """SDMS sent the request to sign in again: the saved session has ended."""


class Sdms:
    def __init__(self, saved: Dict[str, Any]):
        self.http = client.new_http()
        for name, value in (saved.get("services", {}).get("sdms", {}).get("cookies") or {}).items():
            self.http.cookies.set(name, value, domain="sdms.udiseplus.gov.in")
        for name, value in (saved.get("auth_cookies") or {}).items():
            self.http.cookies.set(name, value, domain="auth.udiseplus.gov.in")
        self._next = 0.0
        self._lock = threading.Lock()

    def _pace(self) -> None:
        with self._lock:
            wait = self._next - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next = time.monotonic() + PACE

    def get(self, path: str) -> Any:
        """One read; its 'data'. A slow answer is asked again once; a sign-in page means the session ended."""
        for attempt in (1, 2):
            self._pace()
            headers = {"Accept": "application/json"}
            xsrf = self.http.cookies.get("XSRF-TOKEN", domain="sdms.udiseplus.gov.in")
            if xsrf:
                headers["X-XSRF-TOKEN"] = xsrf
            try:
                resp = self.http.get(BASE + path, headers=headers, timeout=(10, 60), allow_redirects=False)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise client.UdiseError(f"SDMS did not answer ({type(exc).__name__}). Please try again later.") from exc
                time.sleep(5)
                continue
            if resp.status_code in (301, 302, 303, 401) or "auth.udiseplus.gov.in" in resp.headers.get("Location", ""):
                raise SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card, then fetch again.")
            if resp.status_code >= 500 and attempt == 1:
                time.sleep(5)
                continue
            try:
                body = resp.json()
            except ValueError:
                raise client.UdiseError(f"SDMS answered {path.split('/')[1] if '/' in path else path} with HTTP {resp.status_code}.")
            if resp.status_code >= 400 or body.get("status") is False:
                raise client.UdiseError(body.get("message") or f"SDMS answered HTTP {resp.status_code}.")
            return body.get("data")
        raise client.UdiseError("SDMS did not answer. Please try again later.")

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """One save, sent once (never repeated by itself: a save may have gone through even when the answer is
        lost). Returns SDMS's answer: {"status", "message", "data", ...}; a refused save is an UdiseError."""
        self._pace()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        xsrf = self.http.cookies.get("XSRF-TOKEN", domain="sdms.udiseplus.gov.in")
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        try:
            resp = self.http.post(BASE + path, json=body, headers=headers, timeout=(10, 120), allow_redirects=False)
        except requests.RequestException as exc:
            raise client.UdiseError(f"SDMS did not answer the save ({type(exc).__name__}) - check the student on "
                                    "SDMS before trying again.") from exc
        if resp.status_code in (301, 302, 303, 401) or "auth.udiseplus.gov.in" in resp.headers.get("Location", ""):
            raise SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card.")
        try:
            answer = resp.json()
        except ValueError:
            raise client.UdiseError(f"SDMS answered the save with HTTP {resp.status_code}.")
        if resp.status_code >= 400 or answer.get("status") is False:
            raise client.UdiseError(_refusal(answer, resp.status_code))
        return answer

    def post_answer(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """A save whose refusal matters in detail (a new admission: duplicate, age for the class ...): SDMS's whole
        answer, refused or not. Sent once."""
        self._pace()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        xsrf = self.http.cookies.get("XSRF-TOKEN", domain="sdms.udiseplus.gov.in")
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        try:
            resp = self.http.post(BASE + path, json=body, headers=headers, timeout=(10, 120), allow_redirects=False)
        except requests.RequestException as exc:
            raise client.UdiseError(f"SDMS did not answer ({type(exc).__name__}) - check on SDMS whether the student "
                                    "was added before trying again.") from exc
        if resp.status_code in (301, 302, 303, 401) or "auth.udiseplus.gov.in" in resp.headers.get("Location", ""):
            raise SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card.")
        try:
            return resp.json()
        except ValueError:
            raise client.UdiseError(f"SDMS answered with HTTP {resp.status_code}.")

    def get_answer(self, path: str) -> Dict[str, Any]:
        """A request whose refusal matters in detail (an AADHAAR check: SDMS answers 'failed' with the reason): SDMS's
        whole answer, refused or not. Sent once."""
        self._pace()
        headers = {"Accept": "application/json"}
        xsrf = self.http.cookies.get("XSRF-TOKEN", domain="sdms.udiseplus.gov.in")
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        try:
            resp = self.http.get(BASE + path, headers=headers, timeout=(10, 120), allow_redirects=False)
        except requests.RequestException as exc:
            raise client.UdiseError(f"SDMS did not answer ({type(exc).__name__}). Please try again later.") from exc
        if resp.status_code in (301, 302, 303, 401) or "auth.udiseplus.gov.in" in resp.headers.get("Location", ""):
            raise SessionEnded("The SDMS session has ended. Press 'Connect again' on the UDISE+ card.")
        try:
            return resp.json()
        except ValueError:
            raise client.UdiseError(f"SDMS answered with HTTP {resp.status_code}.")

    def key(self) -> str:
        """The key SDMS's pages encrypt an AADHAAR number with (api/key)."""
        found = self.get("api/key")
        if not found:
            raise client.UdiseError("SDMS did not give the key needed to send an AADHAAR number.")
        return str(found)

    def student(self, student_id: int) -> Dict[str, Any]:
        """A student's General Information as the form opens it."""
        return self.get(f"api/cy/students/{student_id}") or {}

    def school_id(self) -> int:
        return int(self.get("api/user")["userRegionId"])

    def school(self, school_id: int) -> Dict[str, Any]:
        return self.get(f"api/cy/school/{school_id}") or {}

    def classes(self, school_id: int) -> list:
        return self.get(f"api/v2/school/total-enr/class-wise/{school_id}") or []

    def students(self, school_id: int) -> list:
        return self.get(f"api/cy/students/all/{school_id}") or []

    def enrolment(self, student_id: int) -> Optional[Dict[str, Any]]:
        return self.get(f"api/v2/students/enrolment/{student_id}")

    def facility(self, student_id: int) -> Optional[Dict[str, Any]]:
        return self.get(f"api/v2/students/facility/{student_id}")

    def mother_tongues(self, state_id: int) -> list:
        return self.get(f"api/cy/masters/motherTongue/{state_id}") or []

    def media(self, school_id: int) -> list:
        return self.get(f"api/cy/masters/school/moi/{school_id}") or []


def session_label(school: Dict[str, Any]) -> str:
    """The session as SDMS names it: yearId 13 is '2026-27' (SDMS's own list: 10 = 2023-24 ... 14 = 2027-28).
    A school's session dates may differ (Nov-Oct in winter-zone schools); the name follows the yearId."""
    year_id = school.get("yearId")
    if isinstance(year_id, int) and year_id > 0:
        start = 2013 + year_id
        return f"{start}-{(start + 1) % 100:02d}"
    return "current session"


def _refusal(answer: Dict[str, Any], status: int) -> str:
    """SDMS's reason for refusing a save, in its own words (a message, or its field errors)."""
    parts = []
    if answer.get("message"):
        parts.append(str(answer["message"]))
    errors = answer.get("errors") or answer.get("error") or (answer.get("data") if isinstance(answer.get("data"), dict) and answer.get("status") is False else None)
    if isinstance(errors, dict):
        parts += [f"{k}: {v}" for k, v in errors.items()]
    elif isinstance(errors, list):
        parts += [str(e.get("message") or e) if isinstance(e, dict) else str(e) for e in errors]
    elif errors:
        parts.append(str(errors))
    return "SDMS did not accept it: " + ("; ".join(parts) if parts else f"HTTP {status}")


def encrypt(text: str, key_b64: str) -> str:
    """As SDMS's pages do (CryptoJS): AES-ECB, the key base64-decoded, PKCS7 padding, the result in base64."""
    import base64
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = base64.b64decode(key_b64)
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode("ascii")
