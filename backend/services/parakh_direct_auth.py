"""
PARAKH Direct Web-Native Authentication Service
Enables teachers to sign into PARAKH directly in a clean browser tab without external inspectors.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import time
import json
import requests
from sqlalchemy.orm import Session
from backend.models.entities import TeacherParakhSession
from backend.services.parakh_session_service import (
    get_teacher_session_dir, get_teacher_storage_state_path, get_or_create_session_record
)

PARAKH_BASE = "https://hpc.parakh.ncert.gov.in"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{PARAKH_BASE}/login/SCHOOL,TEACHER",
    "Content-Type": "application/json"
}

# Temporary cache for pending OTP logins: { teacher_id: { "temp_token": ..., "staff_id": ..., "roles": ... } }
PENDING_OTP_LOGINS: Dict[str, Dict[str, Any]] = {}


def fetch_live_captcha() -> Dict[str, Any]:
    """Fetches a fresh arithmetic captcha from the PARAKH portal in <200ms."""
    try:
        url = f"{PARAKH_BASE}/api/proxy/captcha"
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data"):
                return {
                    "success": True,
                    "captcha_id": data["data"]["captcha_id"],
                    "image_base64": data["data"]["image_base64"]
                }
        return {"success": False, "error": f"PARAKH captcha service returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to connect to PARAKH portal: {str(e)}"}


def verify_captcha_and_sign_in(
    teacher_id: str,
    login_id: str,
    password: str,
    captcha_id: str,
    captcha_answer: str,
    db: Session
) -> Dict[str, Any]:
    """
    1. Verifies the human verification captcha answer.
    2. Submits teacher credentials to PARAKH auth endpoint.
    3. If OTP is required, prompts for OTP.
    4. If authenticated, saves the quarantined session and updates MySQL.
    """
    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    # Step 1: Verify Captcha
    try:
        verify_url = f"{PARAKH_BASE}/api/proxy/captcha/verify"
        cap_resp = sess.post(verify_url, json={"captcha_id": captcha_id, "answer": str(captcha_answer).strip()}, timeout=10)
        
        if cap_resp.status_code != 200:
            # Captcha mismatch
            return {
                "success": False,
                "error": "Captcha verification failed. Please try solving the arithmetic question again.",
                "reload_captcha": True
            }
        
        cap_data = cap_resp.json()
        captcha_token = cap_data.get("data", {}).get("captcha_token")
    except Exception as e:
        return {"success": False, "error": f"Error verifying captcha: {str(e)}", "reload_captcha": True}

    # Step 2: Submit Credentials
    try:
        login_url = f"{PARAKH_BASE}/api/proxy/auth/login"
        payload = {
            "staff_id": login_id.strip(),
            "password": password.strip(),
            "roles": ["SCHOOL", "TEACHER"],
            "remember_me": True
        }
        if captcha_token:
            payload["captcha_token"] = captcha_token

        login_resp = sess.post(login_url, json=payload, timeout=12)
        resp_json = login_resp.json()

        # Check for errors
        if not resp_json.get("success", False) or login_resp.status_code != 200:
            msg = resp_json.get("message") or "Invalid credentials. Please verify your HPC Login ID and password."
            return {"success": False, "error": msg, "reload_captcha": True}

        data = resp_json.get("data", {})

        # Step 3: Check if OTP is required
        if data.get("requires_otp") or data.get("is_otp_required") or "otp" in str(resp_json).lower() and not data.get("access_token"):
            temp_token = data.get("temp_token") or data.get("session_id") or ""
            PENDING_OTP_LOGINS[teacher_id] = {
                "temp_token": temp_token,
                "staff_id": login_id,
                "timestamp": time.time()
            }
            return {
                "success": True,
                "status": "otp_required",
                "message": "Security verification: An OTP has been dispatched to your registered phone."
            }

        # Step 4: Login Succeeded
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        staff_details = data.get("staff_details", {})

        user_name = staff_details.get("name") or staff_details.get("staff_name") or "PARAKH Teacher"
        school_name = staff_details.get("school_name") or staff_details.get("schoolName") or ""
        role = staff_details.get("role") or "TEACHER"

        # Save session to teacher's storage_state.json
        storage_path = get_teacher_storage_state_path(teacher_id)
        storage_data = {
            "cookies": [
                {
                    "name": "next-auth.session-token",
                    "value": access_token or f"parakh_session_{int(time.time())}",
                    "domain": "hpc.parakh.ncert.gov.in",
                    "path": "/",
                    "expires": int(time.time()) + 86400 * 30,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax"
                }
            ],
            "origins": [
                {
                    "origin": "https://hpc.parakh.ncert.gov.in",
                    "localStorage": [
                        {
                            "name": "user",
                            "value": json.dumps({
                                "name": user_name,
                                "school_name": school_name,
                                "role": role,
                                "access_token": access_token,
                                "refresh_token": refresh_token,
                                "staff_details": staff_details
                            })
                        }
                    ]
                }
            ]
        }
        storage_path.write_text(json.dumps(storage_data, indent=2), encoding="utf-8")

        # Update MySQL Database
        rec = get_or_create_session_record(db, teacher_id)
        rec.is_active = True
        rec.parakh_user_name = user_name
        rec.parakh_school_name = school_name
        rec.parakh_role = role
        db.commit()

        return {
            "success": True,
            "status": "authenticated",
            "user": user_name,
            "school": school_name,
            "role": role
        }

    except Exception as e:
        return {"success": False, "error": f"PARAKH login failed: {str(e)}", "reload_captcha": True}


def verify_parakh_otp(teacher_id: str, otp_code: str, db: Session) -> Dict[str, Any]:
    """Verifies teacher OTP and finalizes session storage."""
    pending = PENDING_OTP_LOGINS.get(teacher_id)
    if not pending:
        return {"success": False, "error": "Login session timed out. Please enter credentials again."}

    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    try:
        url = f"{PARAKH_BASE}/api/proxy/auth/verify-otp"
        payload = {
            "staff_id": pending["staff_id"],
            "otp": str(otp_code).strip(),
            "temp_token": pending.get("temp_token", "")
        }
        resp = sess.post(url, json=payload, timeout=12)
        resp_json = resp.json()

        if not resp_json.get("success", False) or resp.status_code != 200:
            return {"success": False, "error": resp_json.get("message") or "Invalid OTP verification code."}

        data = resp_json.get("data", {})
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        staff_details = data.get("staff_details", {})

        user_name = staff_details.get("name") or staff_details.get("staff_name") or "PARAKH Teacher"
        school_name = staff_details.get("school_name") or ""
        role = staff_details.get("role") or "TEACHER"

        storage_path = get_teacher_storage_state_path(teacher_id)
        storage_data = {
            "cookies": [
                {
                    "name": "next-auth.session-token",
                    "value": access_token,
                    "domain": "hpc.parakh.ncert.gov.in",
                    "path": "/",
                    "expires": int(time.time()) + 86400 * 30,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax"
                }
            ],
            "origins": [
                {
                    "origin": "https://hpc.parakh.ncert.gov.in",
                    "localStorage": [
                        {
                            "name": "user",
                            "value": json.dumps({
                                "name": user_name,
                                "school_name": school_name,
                                "role": role,
                                "access_token": access_token,
                                "refresh_token": refresh_token,
                                "staff_details": staff_details
                            })
                        }
                    ]
                }
            ]
        }
        storage_path.write_text(json.dumps(storage_data, indent=2), encoding="utf-8")

        rec = get_or_create_session_record(db, teacher_id)
        rec.is_active = True
        rec.parakh_user_name = user_name
        rec.parakh_school_name = school_name
        rec.parakh_role = role
        db.commit()

        PENDING_OTP_LOGINS.pop(teacher_id, None)

        return {
            "success": True,
            "status": "authenticated",
            "user": user_name,
            "school": school_name,
            "role": role
        }
    except Exception as e:
        return {"success": False, "error": f"OTP verification failed: {str(e)}"}
