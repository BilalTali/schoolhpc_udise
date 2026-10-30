"""
UDISE+ sign-in, shared by its four services.

All four sign in at auth.udiseplus.gov.in (one OAuth server, single sign-on): username, password and a 6-character
image captcha that the PERSON reads and types (never read by the app), then an OTP when UDISE+ asks for one. Once
signed in there, each service is opened through its own OAuth start and keeps its own session: cookies (SDMS) or a
token the service hands its web app at the end of the redirects (Profile, Teacher: "#/auth-redirection?code=...").

begin()          opens the sign-in page: its form and the captcha picture
submit()         sends username, password and captcha (then submit_otp() when an OTP is asked for)
open_services()  opens every service with the signed-in connection and keeps what each hands back
Nothing here writes to UDISE+. Every step is recorded for diagnostics as addresses and NAMES only (no values).
"""
import base64
import re
import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urljoin, urlsplit

import requests

AUTH = "https://auth.udiseplus.gov.in"
USER_AGENT = "TeacherAssist/3.0 (school HPC and UDISE+ helper)"   # says what it is
TIMEOUT = (10, 40)
MAX_HOPS = 15

# How each service starts its sign-in (each is what that service's own "Login" button opens).
SERVICES: Dict[str, Dict[str, str]] = {
    "dcf": {"name": "UDISE+ data capture", "host": "udiseplus.gov.in",
            "start": f"{AUTH}/oauth2/authorize?response_type=code&client_id=ud-app&scope=read"
                     "&redirect_uri=https://udiseplus.gov.in/ud/signInByOAuth"},
    "profile": {"name": "School Profile & Facilities", "host": "profile.udiseplus.gov.in",
                "start": "https://profile.udiseplus.gov.in/udiseplus/sso/code/login"},
    "teacher": {"name": "Teacher module", "host": "teacher.udiseplus.gov.in",
                "start": "https://teacher.udiseplus.gov.in/teacher_module_backend/sso/code/login"},
    "sdms": {"name": "Student module (SDMS)", "host": "sdms.udiseplus.gov.in",
             "start": "https://sdms.udiseplus.gov.in/p0/oauth2/login"},
}
SIGN_IN_START = SERVICES["sdms"]["start"]           # any service's start leads to the shared sign-in page

# what the sign-in page's address says after a refused attempt
LOGIN_ERRORS = {
    "captchaError": "The captcha answer was not right.",
    "locked": "UDISE+ has locked this account for a while after wrong passwords. Try again later on the UDISE+ website.",
    "otpLimitExceeded": "Too many OTPs were asked for. Try again later.",
    "sessionExpired": "The sign-in page timed out. Start again.",
    "sessionInvalid": "The sign-in page timed out. Start again.",
    "expired": "The sign-in page timed out. Start again.",
    "error": "UDISE+ did not accept the username or password.",
}


class UdiseError(Exception):
    pass


class _Forms(HTMLParser):
    """Every form on a page: its action, method and inputs (name -> value), and the page title."""

    def __init__(self):
        super().__init__()
        self.forms: List[Dict[str, Any]] = []
        self.title, self._in_title = "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.forms.append({"action": a.get("action") or "", "method": (a.get("method") or "get").lower(), "inputs": {}})
        elif tag == "input" and self.forms and a.get("name"):
            kind = (a.get("type") or "text").lower()
            if kind in ("radio", "checkbox") and "checked" not in a:
                self.forms[-1]["inputs"].setdefault(a["name"], None)
            else:
                self.forms[-1]["inputs"][a["name"]] = a.get("value") or ""
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


def _forms(html: str) -> _Forms:
    p = _Forms()
    p.feed(html or "")
    return p


def _shape(url: str) -> Dict[str, Any]:
    """An address for the diagnostics: host, path and the NAMES of its parameters (values are secrets)."""
    parts = urlsplit(url)
    frag = parts.fragment
    frag_path, _, frag_query = frag.partition("?")
    path = re.sub(r";[^/]*", "", parts.path)                 # ";jsessionid=..." in a path is a session code
    return {"host": parts.netloc, "path": path, "query": [k for k, _ in parse_qsl(parts.query, keep_blank_values=True)],
            "fragment": frag_path, "fragment_query": [k for k, _ in parse_qsl(frag_query, keep_blank_values=True)]}


def new_http() -> requests.Session:
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    return http


def follow(http: requests.Session, method: str, url: str, trail: List[Dict[str, Any]], **kwargs) -> requests.Response:
    """A request and every redirect after it, one at a time, so each step is recorded (names only)."""
    resp = None
    for _ in range(MAX_HOPS):
        try:
            resp = http.request(method, url, allow_redirects=False, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise UdiseError(f"UDISE+ did not answer ({type(exc).__name__}). Please try again in a few minutes.") from exc
        trail.append({**_shape(url), "method": method, "status": resp.status_code,
                      "cookies_set": sorted({c.name for c in resp.cookies})})
        if resp.status_code not in (301, 302, 303, 307, 308) or "Location" not in resp.headers:
            return resp
        url = urljoin(url, resp.headers["Location"])
        if not url.startswith("https://") and urlsplit(url).netloc.endswith("udiseplus.gov.in"):
            url = "https://" + url.split("://", 1)[1]        # the server sometimes says http:// for itself
        if urlsplit(url).netloc.endswith(".gov.in") is False:
            break                                             # never leave UDISE+
        if resp.status_code != 307:
            method, kwargs = "GET", {}
    trail.append({"note": "stopped following redirects", **_shape(url)})
    resp.final_url = url
    return resp


def final_url(resp: requests.Response) -> str:
    return getattr(resp, "final_url", None) or resp.url


def begin(trail: List[Dict[str, Any]]) -> Tuple[requests.Session, Dict[str, Any], bytes]:
    """The sign-in page (through a service's start) and its captcha picture."""
    http = new_http()
    resp = follow(http, "GET", SIGN_IN_START, trail)
    page = _forms(resp.text)
    form = next((f for f in page.forms if "username" in f["inputs"] and "password" in f["inputs"]), None)
    if form is None:
        raise UdiseError("The UDISE+ sign-in page did not load as expected. Please try again later.")
    form["page"] = resp.url
    return http, form, captcha(http, trail)


def captcha(http: requests.Session, trail: List[Dict[str, Any]]) -> bytes:
    url = f"{AUTH}/captcha-image?ts={int(time.time() * 1000)}"
    try:
        resp = http.get(url, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise UdiseError(f"UDISE+ did not answer ({type(exc).__name__}). Please try again in a few minutes.") from exc
    trail.append({**_shape(url), "method": "GET", "status": resp.status_code, "type": resp.headers.get("Content-Type", "")})
    if not resp.ok or not resp.content:
        raise UdiseError("UDISE+ did not send a captcha picture. Please try again.")
    return resp.content


def picture(content: bytes) -> str:
    kind = "image/png" if content[:4] == b"\x89PNG" else "image/jpeg" if content[:2] == b"\xff\xd8" else "image/png"
    return f"data:{kind};base64,{base64.b64encode(content).decode('ascii')}"


def _outcome(resp: requests.Response, trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Where a sign-in step ended: signed in, an OTP to type, or refused (with the reason)."""
    url = final_url(resp)
    shape = _shape(url)
    page = _forms(resp.text if "html" in resp.headers.get("Content-Type", "") else "")
    otp_form = next((f for f in page.forms if any(re.search(r"otp", k, re.I) for k in f["inputs"])), None)
    if otp_form is not None:
        otp_form["page"] = url
        trail.append({"note": "otp page", "form_inputs": sorted(otp_form["inputs"]), "title": page.title})
        return {"status": "otp_required", "form": otp_form}
    if shape["host"] == urlsplit(AUTH).netloc and shape["path"].rstrip("/") == "/login":
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))   # "?captchaError" has no value
        reason = next((LOGIN_ERRORS[k] for k in LOGIN_ERRORS if k in query), None)
        trail.append({"note": "back on the sign-in page", "title": page.title})
        return {"status": "refused", "error": reason or "UDISE+ did not accept the sign-in.",
                "captcha_wrong": "captchaError" in query}
    if shape["host"] == urlsplit(AUTH).netloc:
        trail.append({"note": "unexpected page on the sign-in server", "title": page.title,
                      "forms": [sorted(f["inputs"]) for f in page.forms]})
        return {"status": "refused", "error": "UDISE+ showed a page this app does not know yet. The diagnostics were kept."}
    return {"status": "signed_in"}


def submit(http: requests.Session, form: Dict[str, Any], username: str, password: str, answer: str,
           trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = {k: v for k, v in form["inputs"].items() if v is not None}
    data.update({"username": username.strip(), "password": password, "captcha": answer.strip(), "captchaMode": "image"})
    return _outcome(follow(http, "POST", urljoin(form["page"], form["action"] or "/login"), trail, data=data), trail)


def submit_otp(http: requests.Session, form: Dict[str, Any], otp: str, trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = {k: v for k, v in form["inputs"].items() if v is not None}
    field = next(k for k in form["inputs"] if re.search(r"otp", k, re.I))
    data[field] = otp.strip()
    method = "POST" if form["method"] == "post" else "GET"
    target = urljoin(form["page"], form["action"] or form["page"])
    resp = follow(http, method, target, trail, **({"data": data} if method == "POST" else {"params": data}))
    return _outcome(resp, trail)


def _handed_token(url: str) -> Optional[Dict[str, Any]]:
    """Profile / Teacher: the end of the redirects carries the web app's session as base64 JSON in 'code'."""
    frag_query = urlsplit(url).fragment.partition("?")[2]
    code = dict(parse_qsl(frag_query)).get("code") or dict(parse_qsl(urlsplit(url).query)).get("code")
    if not code:
        return None
    try:
        import json
        return json.loads(base64.b64decode(code + "=" * (-len(code) % 4)).decode("utf-8"))
    except Exception:
        return None


def open_services(http: requests.Session) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Opens every service with the signed-in connection: {service: what it handed back}, {service: its trail}."""
    found, trails = {}, {}
    for key, svc in SERVICES.items():
        trail: List[Dict[str, Any]] = []
        try:
            resp = follow(http, "GET", svc["start"], trail)
            url = final_url(resp)
            shape = _shape(url)
            on_sign_in = shape["host"] == urlsplit(AUTH).netloc
            token = _handed_token(url)
            cookies = {c.name: c.value for c in http.cookies if c.domain.lstrip(".").endswith(svc["host"])}
            connected = not on_sign_in and resp.status_code < 400 and bool(token or cookies or shape["host"] == svc["host"])
            found[key] = {"connected": connected, "token": token, "cookies": cookies, "landed": url if connected else "",
                          "why": "" if connected else ("UDISE+ asked to sign in again for this service" if on_sign_in
                                                       else f"the service answered HTTP {resp.status_code}")}
            trail.append({"note": "result", "connected": connected, "token_fields": sorted(token) if token else [],
                          "service_cookies": sorted(cookies)})
        except UdiseError as exc:
            found[key] = {"connected": False, "token": None, "cookies": {}, "landed": "", "why": str(exc)}
        trails[key] = trail
    return found, trails
