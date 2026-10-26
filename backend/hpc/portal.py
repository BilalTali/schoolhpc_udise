"""
HTTP client for the PARAKH HPC portal (https://hpc.parakh.ncert.gov.in).

Everything goes through the portal's own JSON API (the same calls its web pages make),
so no browser is needed:

    login            captcha -> /auth/login  (-> /auth/verify-otp when OTP is required)
    roster           GET  /states/{st}/districts/{d}/schools/{s}/teachers/{t}/hpc/{STAGE}
    student / part   GET  /states/{st}/hpc/{ay}/{STAGE}/{student_id}[?hpc_col=part_x]
    save part        PATCH /states/{st}/hpc/{ay}/{STAGE}/{student_id}
"""
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from backend.config import PORTAL_MAX_PER_SECOND
from backend.hpc import captcha

BASE_URL = "https://hpc.parakh.ncert.gov.in"
API = f"{BASE_URL}/api/proxy"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/login/SCHOOL,TEACHER",
}
STAGES = {"foundational": "FOUNDATIONAL", "preparatory": "PREPARATORY", "middle": "MIDDLE"}


class PortalError(Exception):
    """The portal rejected a request (bad credentials, expired session, validation error...)."""


class OtpRequired(Exception):
    """Login needs an OTP; pass `pending` back to verify_otp()."""

    def __init__(self, pending: Dict[str, Any]):
        super().__init__("OTP required")
        self.pending = pending


def stage_code(stage: str) -> str:
    """'Middle' / 'middle' / 'MIDDLE' -> 'MIDDLE'."""
    code = STAGES.get(stage.strip().lower())
    if not code:
        raise ValueError(f"Unsupported stage {stage!r}; expected one of {list(STAGES)}")
    return code


@dataclass
class Session:
    """An authenticated portal session (what /auth/login returns)."""
    access_token: str
    staff: Dict[str, Any] = field(default_factory=dict)
    refresh_token: str = ""
    saved_at: float = 0.0

    @property
    def name(self) -> str:
        return self.staff.get("name") or self.staff.get("staff_name") or "HPC User"

    @property
    def school_name(self) -> str:
        return self.staff.get("school_name") or ""

    @property
    def role(self) -> str:
        return self.staff.get("role") or ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.saved_at = time.time()
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["Session"]:
        if not path.exists():
            return None
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None


def _http() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except ValueError:
        raise PortalError(f"Portal returned HTTP {resp.status_code} (not JSON): {resp.text[:200]}")


def _session_from_login_data(data: Dict[str, Any]) -> Session:
    if not data.get("access_token"):
        raise PortalError("Login response did not contain an access token.")
    return Session(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        staff=data.get("staff_details") or {},
    )


def begin_login() -> Tuple[requests.Session, str, str]:
    """Reads a captcha from PARAKH: (connection to keep for the answer, captcha_id, image as base64 PNG)."""
    http = _http()
    body = _json(http.get(f"{API}/captcha", timeout=15))
    cap = body.get("data") or {}
    if not cap.get("captcha_id") or not cap.get("image_base64"):
        raise PortalError("PARAKH did not send a captcha. Please try again in a minute.")
    return http, str(cap["captcha_id"]), str(cap["image_base64"])


def answer_captcha(http: requests.Session, captcha_id: str, answer: str) -> str:
    """Checks the answer a person typed; returns PARAKH's captcha_token."""
    resp = http.post(f"{API}/captcha/verify", json={"captcha_id": captcha_id, "answer": str(answer).strip()}, timeout=15)
    if not resp.ok:
        raise PortalError("The captcha answer was not accepted.")
    return (_json(resp).get("data") or {}).get("captcha_token", "")


def login_with_token(http: requests.Session, login_id: str, password: str, captcha_token: str) -> Session:
    """Logs in after the captcha was answered. Raises OtpRequired if the portal asks for an OTP."""
    payload = {"staff_id": login_id.strip(), "password": password.strip(),
               "roles": ["SCHOOL", "TEACHER"], "remember_me": True, "captcha_token": captcha_token}
    resp = http.post(f"{API}/auth/login", json=payload, timeout=20)
    body = _json(resp)
    if not resp.ok or not body.get("success"):
        raise PortalError(body.get("message") or f"Login failed (HTTP {resp.status_code}).")
    data = body.get("data") or {}
    if not data.get("access_token"):
        raise OtpRequired({"staff_id": login_id.strip(), "login_data": data})
    return _session_from_login_data(data)


def _solve_captcha(http: requests.Session, attempts: int = 5) -> str:
    """UNSUPPORTED automatic path (HPC_AUTO_CAPTCHA): reads captchas until one is accepted."""
    last = "no attempt made"
    for _ in range(attempts):
        body = _json(http.get(f"{API}/captcha", timeout=15))
        cap = body.get("data") or {}
        answer, expr = captcha.solve_base64(cap.get("image_base64", ""))
        if answer is None:
            last = f"could not read captcha ({expr!r})"
            continue
        resp = http.post(f"{API}/captcha/verify",
                         json={"captcha_id": cap.get("captcha_id"), "answer": str(answer)}, timeout=15)
        if resp.ok:
            return (_json(resp).get("data") or {}).get("captcha_token", "")
        last = f"captcha {expr!r}={answer} rejected (HTTP {resp.status_code})"
    raise PortalError(f"Captcha failed after {attempts} attempts: {last}")


def login(login_id: str, password: str) -> Session:
    """UNSUPPORTED automatic login (the app reads the captcha). Only used when HPC_AUTO_CAPTCHA is on."""
    http = _http()
    return login_with_token(http, login_id, password, _solve_captcha(http))


def verify_otp(pending: Dict[str, Any], otp: str) -> Session:
    """Completes a login that raised OtpRequired."""
    data = pending.get("login_data") or {}
    payload = {"staff_id": pending["staff_id"], "otp": otp.strip(),
               "temp_token": data.get("temp_token") or data.get("session_id") or ""}
    resp = _http().post(f"{API}/auth/verify-otp", json=payload, timeout=20)
    body = _json(resp)
    if not resp.ok or not body.get("success"):
        raise PortalError(body.get("message") or "Invalid OTP.")
    return _session_from_login_data(body.get("data") or {})


class Portal:
    """Authenticated API calls for one teacher/school session."""

    def __init__(self, session: Session, on_refresh: Callable[[Session], None] = lambda s: None):
        """on_refresh is called with the new Session whenever the token is renewed (so it can be saved)."""
        self.session = session
        self.on_refresh = on_refresh
        self.http = _http()
        self.http.headers["Authorization"] = f"Bearer {session.access_token}"
        self._lock = threading.Lock()
        self._pace_lock = threading.Lock()
        self._next_at = 0.0
        self.min_interval = 1.0 / max(PORTAL_MAX_PER_SECOND, 0.1)
        self.relogin: Optional[Callable[[], Session]] = None   # fallback when the refresh token is rejected too
        staff = session.staff
        self.state = staff.get("state_code_internal") or "jk"
        self.ay = str(staff.get("school_cur_ay_code") or "")
        self.district_id = staff.get("district_id")
        self.school_id = staff.get("school_id")
        self.staff_id = staff.get("staff_id")

    def refresh(self, rejected_token: str) -> bool:
        """Renews the access token with the refresh token, like the portal's own pages do."""
        with self._lock:
            if self.session.access_token != rejected_token:
                return True                      # another thread already renewed it
            resp = _http().post(f"{API}/auth/refresh-token", timeout=20,
                                headers={"Authorization": f"Bearer {self.session.refresh_token}"})
            data = (_json(resp).get("data") or {}) if resp.ok else {}
            if data.get("access_token"):
                self.session.access_token = data["access_token"]
                self.session.refresh_token = data.get("refresh_token") or self.session.refresh_token
                self.session.staff = data.get("staff_details") or self.session.staff
            elif self.relogin:
                try:
                    fresh = self.relogin()
                except Exception:
                    return False
                self.session.access_token, self.session.refresh_token = fresh.access_token, fresh.refresh_token
                self.session.staff = fresh.staff or self.session.staff
            else:
                return False
            self.http.headers["Authorization"] = f"Bearer {self.session.access_token}"
            self.on_refresh(self.session)
            return True

    def _pace(self) -> None:
        """Keeps this session to PORTAL_MAX_PER_SECOND requests a second, across all its threads."""
        with self._pace_lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        token = self.session.access_token
        self._pace()
        resp = self.http.request(method, f"{API}{path}", timeout=30, **kwargs)
        if resp.status_code == 401 and self.refresh(token):
            self._pace()
            resp = self.http.request(method, f"{API}{path}", timeout=30, **kwargs)
        self.last_status = resp.status_code                 # for callers that report it (e.g. phase 3b)
        if resp.status_code == 401:
            raise PortalError("Portal session expired. Please start the HPC session again.")
        if resp.status_code == 403:
            raise PortalError("The portal does not allow this account to open this record.")
        if resp.status_code == 204:
            return {"success": True, "data": {}}      # e.g. an empty roster
        body = _json(resp)
        if not resp.ok or body.get("success") is False:
            raise PortalError(body.get("message") or f"{method} {path} failed (HTTP {resp.status_code}).")
        return body

    def is_valid(self) -> bool:
        try:
            self.roster_page("Preparatory" if "PREPARATORY" in (self.session.staff.get("hpc_stage") or [])
                             else "Middle", page_no=1, page_size=1)
            return True
        except Exception:
            return False

    def roster_page(self, stage: str, page_no: int, page_size: int = 100) -> Dict[str, Any]:
        path = (f"/states/{self.state}/districts/{self.district_id}/schools/{self.school_id}"
                f"/teachers/{self.staff_id}/hpc/{stage_code(stage)}")
        return self._request("GET", path, params={"page_no": page_no, "page_size": page_size}).get("data") or {}

    def owns(self, record: Dict[str, Any]) -> bool:
        """Whether this teacher is class teacher for the student's grade/section (the portal's edit rule)."""
        mapping = self.session.staff.get("grade_section_mapping")
        if not isinstance(mapping, list) or not mapping:
            return True                           # school accounts have no mapping
        return any(str(m.get("grd")) == str(record.get("grade_id")) and str(m.get("sec")) == str(record.get("section_id"))
                   for m in mapping)

    def roster(self, stage: str) -> List[Dict[str, Any]]:
        """Students on this teacher's roster for a stage that the teacher may edit."""
        records, seen, page_no = [], set(), 1
        while page_no <= 50:
            data = self.roster_page(stage, page_no)
            page = data.get("records") or []
            new = [r for r in page if str(r.get("id")) not in seen]
            seen.update(str(r.get("id")) for r in new)
            records.extend(new)
            total = data.get("total_count") or data.get("total_records")
            if not new or len(page) < 100 or (total and len(records) >= int(total)):
                break
            page_no += 1
        return [r for r in records if self.owns(r)]

    def student(self, stage: str, student_id: str, hpc_col: Optional[str] = None) -> Dict[str, Any]:
        """A student's HPC record; with hpc_col, just that part (its data has 'formdata')."""
        params = {"hpc_col": hpc_col} if hpc_col else None
        return self._request("GET", f"/states/{self.state}/hpc/{self.ay}/{stage_code(stage)}/{student_id}",
                             params=params).get("data") or {}

    # -- Activity Bank (read-only) ---------------------------------------------
    def activity_bank_page(self, page_no: int = 1, page_size: int = 200, stage: Optional[str] = None) -> Dict[str, Any]:
        """One page of PARAKH's global Activity Bank: {"records": [...], "count": total}."""
        params = {"page_no": page_no, "page_size": page_size}
        if stage:
            params["hpc_stage"] = stage_code(stage)
        return self._request("GET", "/country/activities", params=params).get("data") or {}

    def my_activities_page(self, stage: str, page_no: int = 1, page_size: int = 200) -> Dict[str, Any]:
        """One page of the signed-in teacher's own activities ("My activities" on the portal)."""
        role = self.session.staff.get("role") or "TEACHER"
        path = (f"/states/{self.state}/districts/{self.district_id}/schools/{self.school_id}"
                f"/{self.ay}/{role}/{self.staff_id}/activities")
        return self._request("GET", path, params={"hpc_stage": stage_code(stage), "page_no": page_no,
                                                  "page_size": page_size}).get("data") or {}

    def activity_categories(self, stage: str) -> List[Dict[str, Any]]:
        """A stage's subjects/domains: [{"id": 88, "ent_code": "PSLS1", "ent_caption": ...}, ...]."""
        return self._request("GET", f"/hpc/activity-categories/{stage_code(stage)}").get("data") or []

    def save_part(self, stage: str, student_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """PATCHes one part of a student's HPC; payload has the same keys the portal page sends."""
        return self._request("PATCH", f"/states/{self.state}/hpc/{self.ay}/{stage_code(stage)}/{student_id}",
                             json=payload)
