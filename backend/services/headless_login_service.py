"""
Headless PARAKH In-Tab Login Bridge
Manages headless browser instances for teachers logging in via the web tab.
"""
from typing import Dict, Any, Optional
import time
from playwright.sync_api import sync_playwright, BrowserContext, Page
from backend.config import SESSIONS_DIR
from backend.services.parakh_session_service import (
    get_teacher_session_dir, get_teacher_storage_state_path, get_or_create_session_record
)

class HeadlessTeacherLoginManager:
    """Keeps an in-memory map of active login sessions for teachers."""
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def start_login_session(self, teacher_id: str) -> Dict[str, Any]:
        """
        Starts a headless page for this teacher, navigates to PARAKH login,
        and returns the captcha image (base64) and captcha id.
        """
        # Cleanup previous if any
        self.cleanup(teacher_id)

        session_dir = get_teacher_session_dir(teacher_id)
        profile_dir = session_dir / "browser_profile"

        p = sync_playwright().start()
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            ignore_default_args=["--enable-automation"]
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            page.goto("https://hpc.parakh.ncert.gov.in/login/SCHOOL,TEACHER", wait_until="networkidle", timeout=30000)
            
            # Find captcha image
            captcha_img = page.wait_for_selector(".captcha-question img", timeout=8000)
            captcha_src = captcha_img.get_attribute("src") if captcha_img else ""
            
            self._sessions[teacher_id] = {
                "playwright": p,
                "context": ctx,
                "page": page,
                "created_at": time.time(),
                "profile_dir": profile_dir
            }

            return {
                "success": True,
                "captcha_image": captcha_src,
                "message": "Login form initialized."
            }
        except Exception as e:
            try:
                ctx.close()
                p.stop()
            except Exception:
                pass
            return {"success": False, "error": f"Failed to reach PARAKH login: {str(e)}"}

    def refresh_captcha(self, teacher_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(teacher_id)
        if not sess:
            return self.start_login_session(teacher_id)

        page: Page = sess["page"]
        try:
            reload_btn = page.query_selector('button[aria-label="Reload Captcha"]')
            if reload_btn:
                reload_btn.click()
                time.sleep(1)
            img = page.query_selector(".captcha-question img")
            src = img.get_attribute("src") if img else ""
            return {"success": True, "captcha_image": src}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_credentials(self, teacher_id: str, login_id: str, password: str, captcha_answer: str, db: Any) -> Dict[str, Any]:
        sess = self._sessions.get(teacher_id)
        if not sess:
            return {"success": False, "error": "Login session expired. Please reload captcha."}

        page: Page = sess["page"]
        ctx: BrowserContext = sess["context"]
        p = sess["playwright"]

        try:
            login_input = page.query_selector('input[placeholder*="login ID"]')
            pass_input = page.query_selector('input[placeholder="Password"]')
            captcha_input = page.query_selector('input[placeholder="Captcha"]')
            submit_btn = page.query_selector('button[type="submit"]')

            if not (login_input and pass_input and captcha_input and submit_btn):
                return {"success": False, "error": "Login form fields not found."}

            login_input.fill(login_id)
            pass_input.fill(password)
            captcha_input.fill(captcha_answer)
            time.sleep(0.5)

            submit_btn.click()
            time.sleep(3)

            # Check if there is an error toast
            toasts = page.query_selector_all('.Toastify__toast-body')
            for t in toasts:
                txt = t.inner_text().strip()
                if txt and ("fail" in txt.lower() or "error" in txt.lower() or "not match" in txt.lower() or "invalid" in txt.lower()):
                    return {"success": False, "error": txt}

            # Check if OTP input is present
            otp_input = page.query_selector('input[placeholder*="OTP"], input[name*="otp"], input[type="tel"]')
            if otp_input:
                return {
                    "success": True,
                    "status": "otp_required",
                    "message": "OTP verification code has been sent to your registered mobile number."
                }

            # Check if already reached dashboard
            curr_url = page.url
            if "/hpc-dashboard" in curr_url or "/hpc/" in curr_url or "/dashboard" in curr_url:
                storage_path = get_teacher_storage_state_path(teacher_id)
                ctx.storage_state(path=str(storage_path))

                # Extract user details
                user_name = "PARAKH Teacher"
                school_name = ""
                try:
                    s_data = page.evaluate("async () => { const r = await fetch('/api/auth/session'); return await r.json(); }")
                    if s_data and s_data.get("user"):
                        user_name = s_data["user"].get("name") or s_data["user"].get("username") or user_name
                        school_name = s_data["user"].get("school_name") or ""
                except Exception:
                    pass

                rec = get_or_create_session_record(db, teacher_id)
                rec.is_active = True
                rec.parakh_user_name = user_name
                rec.parakh_school_name = school_name
                db.commit()

                self.cleanup(teacher_id)
                return {
                    "success": True,
                    "status": "authenticated",
                    "user": user_name,
                    "school": school_name
                }

            return {"success": False, "error": "Login could not be completed. Check credentials and captcha."}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_otp(self, teacher_id: str, otp_code: str, db: Any) -> Dict[str, Any]:
        sess = self._sessions.get(teacher_id)
        if not sess:
            return {"success": False, "error": "Login session expired. Please start again."}

        page: Page = sess["page"]
        ctx: BrowserContext = sess["context"]

        try:
            otp_input = page.query_selector('input[placeholder*="OTP"], input[name*="otp"], input[type="tel"]')
            if not otp_input:
                return {"success": False, "error": "OTP input field not found on portal page."}

            otp_input.fill(otp_code)
            
            # Submit OTP
            confirm_btn = page.query_selector('button:has-text("Confirm"), button:has-text("Verify"), button:has-text("Submit"), button[type="submit"]')
            if confirm_btn:
                confirm_btn.click()
            time.sleep(3.5)

            # Check error toasts
            toasts = page.query_selector_all('.Toastify__toast-body')
            for t in toasts:
                txt = t.inner_text().strip()
                if txt and ("invalid" in txt.lower() or "error" in txt.lower() or "fail" in txt.lower()):
                    return {"success": False, "error": txt}

            curr_url = page.url
            if "/hpc-dashboard" in curr_url or "/hpc/" in curr_url or "/dashboard" in curr_url:
                storage_path = get_teacher_storage_state_path(teacher_id)
                ctx.storage_state(path=str(storage_path))

                user_name = "PARAKH Teacher"
                school_name = ""
                try:
                    s_data = page.evaluate("async () => { const r = await fetch('/api/auth/session'); return await r.json(); }")
                    if s_data and s_data.get("user"):
                        user_name = s_data["user"].get("name") or s_data["user"].get("username") or user_name
                        school_name = s_data["user"].get("school_name") or ""
                except Exception:
                    pass

                rec = get_or_create_session_record(db, teacher_id)
                rec.is_active = True
                rec.parakh_user_name = user_name
                rec.parakh_school_name = school_name
                db.commit()

                self.cleanup(teacher_id)
                return {
                    "success": True,
                    "status": "authenticated",
                    "user": user_name,
                    "school": school_name
                }

            return {"success": False, "error": "OTP verification did not redirect to dashboard. Please check OTP."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup(self, teacher_id: str):
        sess = self._sessions.pop(teacher_id, None)
        if sess:
            try:
                sess["context"].close()
            except Exception:
                pass
            try:
                sess["playwright"].stop()
            except Exception:
                pass

login_manager = HeadlessTeacherLoginManager()
