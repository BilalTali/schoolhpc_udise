"""
HPC Auto-Login Service
Handles the full PARAKH HPC login flow for both School Admins and Teachers:
  1. Fetch arithmetic captcha from PARAKH
  2. Auto-solve the arithmetic expression (via OCR or text parsing)
  3. Verify captcha answer with PARAKH
  4. Submit credentials (login_id + password + captcha_token)
  5. Handle OTP if required
  6. Persist isolated session storage

Supports retrying captcha up to 3 times if auto-solve fails.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Dict, Any, Optional

import requests
from sqlalchemy.orm import Session

from backend.models.entities import School, Teacher
from backend.services.hpc_session_service import (
    save_school_session, save_teacher_session,
    end_school_hpc_session, end_teacher_hpc_session
)

PARAKH_BASE = "https://hpc.parakh.ncert.gov.in"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{PARAKH_BASE}/login/SCHOOL,TEACHER",
    "Content-Type": "application/json",
}

# In-memory store for pending OTP confirmations: {entity_key: {...}}
# entity_key = "school_{school_id}" or "teacher_{teacher_id}"
PENDING_OTP: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Captcha Fetch & Auto-Solve
# ---------------------------------------------------------------------------

def _fetch_captcha(http_sess: requests.Session) -> Dict[str, Any]:
    """Fetches a fresh arithmetic captcha from PARAKH."""
    try:
        resp = http_sess.get(f"{PARAKH_BASE}/api/proxy/captcha", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data"):
                d = data["data"]
                return {
                    "success": True,
                    "captcha_id": d.get("captcha_id", ""),
                    "image_base64": d.get("image_base64", ""),
                    "question": d.get("question") or d.get("text") or "",
                }
        return {"success": False, "error": f"PARAKH captcha service returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ocr_solve(image_b64: str) -> Optional[str]:
    """Tries pytesseract OCR to extract and solve the arithmetic from the captcha image."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("L")
        # Binarize for cleaner OCR
        img = img.point(lambda p: 0 if p < 140 else 255)
        text = pytesseract.image_to_string(
            img, config="--psm 7 -c tessedit_char_whitelist=0123456789+-*/x=? "
        ).strip()
        return _eval_math(text)
    except Exception:
        return None


def _eval_math(text: str) -> Optional[str]:
    """Parses and evaluates a simple arithmetic expression string."""
    expr = text.replace(" ", "").replace("=", "").replace("?", "").lower()

    m = re.search(r"(\d+)\+(\d+)", expr)
    if m:
        return str(int(m.group(1)) + int(m.group(2)))

    m = re.search(r"(\d+)-(\d+)", expr)
    if m:
        return str(int(m.group(1)) - int(m.group(2)))

    m = re.search(r"(\d+)[*x×](\d+)", expr)
    if m:
        return str(int(m.group(1)) * int(m.group(2)))

    m = re.search(r"(\d+)[/÷](\d+)", expr)
    if m:
        divisor = int(m.group(2))
        if divisor:
            return str(int(m.group(1)) // divisor)

    return None


def _auto_solve_captcha(http_sess: requests.Session, max_attempts: int = 4
                        ) -> Dict[str, Any]:
    """
    Fetches a captcha and auto-solves it.
    Retries up to max_attempts times if solving or verification fails.
    Returns {success, captcha_id, answer, captcha_token} on success.
    """
    last_error = "Unknown error"

    for attempt in range(1, max_attempts + 1):
        cap = _fetch_captcha(http_sess)
        if not cap.get("success"):
            last_error = cap.get("error", "Captcha fetch failed")
            time.sleep(0.5)
            continue

        captcha_id = cap["captcha_id"]
        image_b64 = cap["image_base64"]
        question_text = cap.get("question", "")

        # Try to solve
        answer = None
        if image_b64:
            answer = _ocr_solve(image_b64)
        if answer is None and question_text:
            answer = _eval_math(question_text)

        if answer is None:
            last_error = f"Attempt {attempt}: Could not solve captcha automatically"
            time.sleep(0.3)
            continue

        # Verify with PARAKH
        try:
            v_resp = http_sess.post(
                f"{PARAKH_BASE}/api/proxy/captcha/verify",
                json={"captcha_id": captcha_id, "answer": str(answer)},
                timeout=10,
            )
            if v_resp.status_code == 200:
                v_data = v_resp.json()
                captcha_token = v_data.get("data", {}).get("captcha_token") or ""
                return {
                    "success": True,
                    "captcha_id": captcha_id,
                    "answer": answer,
                    "captcha_token": captcha_token,
                }
            last_error = f"Attempt {attempt}: Captcha verify returned {v_resp.status_code}"
        except Exception as e:
            last_error = f"Attempt {attempt}: {e}"

        time.sleep(0.4)

    return {"success": False, "error": f"Auto-solve failed after {max_attempts} attempts: {last_error}"}


# ---------------------------------------------------------------------------
# Core Login (shared by School and Teacher)
# ---------------------------------------------------------------------------

def _submit_credentials(
    http_sess: requests.Session,
    login_id: str,
    password: str,
    captcha_token: str,
    roles: list,
) -> Dict[str, Any]:
    """Submits credentials to PARAKH login API."""
    payload = {
        "staff_id": login_id.strip(),
        "password": password.strip(),
        "roles": roles,
        "remember_me": True,
    }
    if captcha_token:
        payload["captcha_token"] = captcha_token

    resp = http_sess.post(f"{PARAKH_BASE}/api/proxy/auth/login", json=payload, timeout=15)
    return resp.json(), resp.status_code


# ---------------------------------------------------------------------------
# Public API: School Start Session
# ---------------------------------------------------------------------------

def start_school_hpc_session(school_id: str, login_id: str, password: str,
                              db: Session) -> Dict[str, Any]:
    """
    Full auto-login flow for a School Admin.
    Solves captcha automatically, submits credentials, saves session.
    Returns status: 'authenticated' | 'otp_required' | error
    """
    http_sess = requests.Session()
    http_sess.headers.update(_HEADERS)

    # Step 1: Auto-solve captcha
    cap = _auto_solve_captcha(http_sess)
    if not cap.get("success"):
        return {"success": False, "error": cap.get("error", "Captcha auto-solve failed.")}

    captcha_token = cap.get("captcha_token", "")

    # Step 2: Submit credentials
    try:
        resp_json, status_code = _submit_credentials(
            http_sess, login_id, password, captcha_token,
            roles=["SCHOOL", "TEACHER"]
        )
    except Exception as e:
        return {"success": False, "error": f"PARAKH login request failed: {e}"}

    if not resp_json.get("success") or status_code != 200:
        msg = resp_json.get("message") or "Invalid HPC credentials. Please check Login ID and password."
        return {"success": False, "error": msg, "reload_captcha": True}

    data = resp_json.get("data", {})

    # Step 3a: OTP required
    if (data.get("requires_otp") or data.get("is_otp_required")
            or ("otp" in str(resp_json).lower() and not data.get("access_token"))):
        temp_token = data.get("temp_token") or data.get("session_id") or ""
        PENDING_OTP[f"school_{school_id}"] = {
            "temp_token": temp_token,
            "staff_id": login_id,
            "entity_type": "school",
            "entity_id": school_id,
            "timestamp": time.time(),
        }
        return {
            "success": True,
            "status": "otp_required",
            "message": "Security OTP dispatched to your registered mobile number.",
        }

    # Step 3b: Authenticated directly
    return _finalize_login(data, "school", school_id, db)


# ---------------------------------------------------------------------------
# Public API: Teacher Start Session
# ---------------------------------------------------------------------------

def start_teacher_hpc_session(teacher_id: str, login_id: str, password: str,
                               db: Session) -> Dict[str, Any]:
    """
    Full auto-login flow for a Teacher.
    Solves captcha automatically, submits credentials, saves session.
    """
    http_sess = requests.Session()
    http_sess.headers.update(_HEADERS)

    # Step 1: Auto-solve captcha
    cap = _auto_solve_captcha(http_sess)
    if not cap.get("success"):
        return {"success": False, "error": cap.get("error", "Captcha auto-solve failed.")}

    captcha_token = cap.get("captcha_token", "")

    # Step 2: Submit credentials
    try:
        resp_json, status_code = _submit_credentials(
            http_sess, login_id, password, captcha_token,
            roles=["SCHOOL", "TEACHER"]
        )
    except Exception as e:
        return {"success": False, "error": f"PARAKH login request failed: {e}"}

    if not resp_json.get("success") or status_code != 200:
        msg = resp_json.get("message") or "Invalid HPC credentials. Please check Login ID and password."
        return {"success": False, "error": msg, "reload_captcha": True}

    data = resp_json.get("data", {})

    # Step 3a: OTP required
    if (data.get("requires_otp") or data.get("is_otp_required")
            or ("otp" in str(resp_json).lower() and not data.get("access_token"))):
        temp_token = data.get("temp_token") or data.get("session_id") or ""
        PENDING_OTP[f"teacher_{teacher_id}"] = {
            "temp_token": temp_token,
            "staff_id": login_id,
            "entity_type": "teacher",
            "entity_id": teacher_id,
            "timestamp": time.time(),
        }
        return {
            "success": True,
            "status": "otp_required",
            "message": "Security OTP dispatched to your registered mobile number.",
        }

    # Step 3b: Authenticated directly
    return _finalize_login(data, "teacher", teacher_id, db)


# ---------------------------------------------------------------------------
# OTP Verification (shared)
# ---------------------------------------------------------------------------

def verify_hpc_otp(entity_key: str, otp_code: str, db: Session) -> Dict[str, Any]:
    """
    Verifies OTP for either a school or teacher.
    entity_key: "school_{school_id}" or "teacher_{teacher_id}"
    """
    pending = PENDING_OTP.get(entity_key)
    if not pending:
        return {"success": False, "error": "Login session timed out. Please start the HPC session again."}

    http_sess = requests.Session()
    http_sess.headers.update(_HEADERS)

    try:
        payload = {
            "staff_id": pending["staff_id"],
            "otp": str(otp_code).strip(),
            "temp_token": pending.get("temp_token", ""),
        }
        resp = http_sess.post(f"{PARAKH_BASE}/api/proxy/auth/verify-otp", json=payload, timeout=12)
        resp_json = resp.json()

        if not resp_json.get("success") or resp.status_code != 200:
            return {
                "success": False,
                "error": resp_json.get("message") or "Invalid OTP verification code.",
            }

        data = resp_json.get("data", {})
        result = _finalize_login(
            data, pending["entity_type"], pending["entity_id"], db
        )
        if result.get("success"):
            PENDING_OTP.pop(entity_key, None)
        return result

    except Exception as e:
        return {"success": False, "error": f"OTP verification failed: {e}"}


# ---------------------------------------------------------------------------
# Finalize Login Helper
# ---------------------------------------------------------------------------

def _finalize_login(data: dict, entity_type: str, entity_id: str,
                    db: Session) -> Dict[str, Any]:
    """Extracts tokens/user info from PARAKH response and saves the session."""
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    staff_details = data.get("staff_details", {})

    user_name = (
        staff_details.get("name")
        or staff_details.get("staff_name")
        or "HPC User"
    )
    school_name = (
        staff_details.get("school_name")
        or staff_details.get("schoolName")
        or ""
    )
    role = staff_details.get("role") or entity_type.upper()

    if entity_type == "school":
        save_school_session(
            entity_id, db,
            access_token=access_token,
            user_name=user_name,
            school_name=school_name,
            role=role,
            refresh_token=refresh_token,
            staff_details=staff_details,
        )
    else:
        save_teacher_session(
            entity_id, db,
            access_token=access_token,
            user_name=user_name,
            school_name=school_name,
            role=role,
            refresh_token=refresh_token,
            staff_details=staff_details,
        )

    return {
        "success": True,
        "status": "authenticated",
        "user": user_name,
        "school": school_name,
        "role": role,
    }
