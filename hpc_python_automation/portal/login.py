"""
Login: manages headful browser authentication sessions using persistent Playwright context.
Credentials are never stored or handled by code. The user authenticates manually.
Provides functions to check status, start an interactive login session, and end a session.
"""
from pathlib import Path
from typing import Dict, Any
import time
from playwright.sync_api import Playwright, BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / ".browser_profile"
DASHBOARD_URL = "https://hpc.parakh.ncert.gov.in/en/hpc-dashboard"
LOGIN_URL = "https://hpc.parakh.ncert.gov.in/en"


def cleanup_zombie_browsers():
    """Kills any orphaned chromium processes associated with .browser_profile and removes lock files."""
    import subprocess
    try:
        cmd = """Get-CimInstance Win32_Process -Filter "name='chrome.exe'" | Where-Object { $_.CommandLine -like "*browser_profile*" -or $_.CommandLine -like "*ms-playwright*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"""
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=8)
    except Exception:
        pass

    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        f = PROFILE_DIR / lock
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass


def get_browser_context(p: Playwright, headless: bool = False, profile_dir: Optional[Path] = None) -> BrowserContext:
    """Launches the persistent browser context with user profile retained."""
    target_dir = Path(profile_dir) if profile_dir else PROFILE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean locks on target dir
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        f = target_dir / lock
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    try:
        return p.chromium.launch_persistent_context(
            str(target_dir),
            headless=headless,
            no_viewport=True,
            args=["--start-maximized"],
        )
    except Exception as e:
        if "ProcessSingleton" in str(e) or "used by another process" in str(e):
            print("[WARN] Profile directory locked by previous process. Cleaning up and retrying...")
            cleanup_zombie_browsers()
            time.sleep(1.5)
            return p.chromium.launch_persistent_context(
                str(target_dir),
                headless=headless,
                no_viewport=True,
                args=["--start-maximized"],
            )
        raise e


def check_session_status(headless: bool = True) -> Dict[str, Any]:
    """
    Checks if the current .browser_profile has an active authenticated session.
    Returns dict with logged_in, user, school, role.
    """
    with sync_playwright() as p:
        try:
            ctx = get_browser_context(p, headless=headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=12000)
            time.sleep(1.5)
            cur_url = page.url

            # If client-side router redirected to login page (/en), definitely not logged in
            if cur_url.endswith("/en") or cur_url.endswith("/en/"):
                ctx.close()
                return {"logged_in": False, "user": "", "school": "", "role": "", "url": cur_url}

            if "/hpc-dashboard" in cur_url or "/hpc/" in cur_url:
                session_data = page.evaluate('''async () => {
                    try {
                        const res = await fetch('/api/auth/session');
                        return await res.json();
                    } catch(e) {
                        return null;
                    }
                }''')
                ctx.close()
                if session_data and session_data.get("user"):
                    u = session_data["user"]
                    return {
                        "logged_in": True,
                        "user": u.get("name") or u.get("username") or "Teacher",
                        "school": u.get("school_name", ""),
                        "role": u.get("role_name") or u.get("role") or "TEACHER",
                        "url": cur_url
                    }
            ctx.close()
            return {"logged_in": False, "user": "", "school": "", "role": "", "url": cur_url}
        except Exception as e:
            return {"logged_in": False, "user": "", "school": "", "role": "", "error": str(e)}


def start_interactive_session(timeout_seconds: int = 300) -> Dict[str, Any]:
    """
    Opens a visible (headful) browser window directed to the HPC login page.
    Waits for the user to complete login and reach the dashboard.
    """
    print("\n" + "=" * 60)
    print("[AUTH] OPENING BROWSER FOR MANUAL LOGIN...")
    print("=" * 60)
    print("Please log in with your credentials in the opened browser window.")
    print("Waiting for dashboard to load...\n")

    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(LOGIN_URL)
            page.bring_to_front()

            start = time.time()
            while time.time() - start < timeout_seconds:
                try:
                    if not ctx.pages or ctx.pages[0].is_closed():
                        return {"success": False, "error": "Browser window was closed before login was completed."}
                    cur = page.url
                except Exception:
                    return {"success": False, "error": "Browser window was closed."}

                # Check if navigated away from login to authenticated page
                if ("/hpc-dashboard" in cur or "/hpc/" in cur or "/profile" in cur) and not (cur.endswith("/en") or cur.endswith("/en/")):
                    time.sleep(1.5)
                    try:
                        session_data = page.evaluate('''async () => {
                            try {
                                const res = await fetch('/api/auth/session');
                                return await res.json();
                            } catch(e) {
                                return null;
                            }
                        }''')
                        if session_data and session_data.get("user"):
                            u = session_data.get("user", {})
                            print("[OK] Session successfully established!")
                            return {
                                "success": True,
                                "user": u.get("name") or "Teacher",
                                "school": u.get("school_name", ""),
                                "role": u.get("role_name", "TEACHER")
                            }
                    except Exception:
                        pass
                time.sleep(1.5)

            return {"success": False, "error": "Login timed out after 5 minutes."}
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def end_session() -> bool:
    """Logs out and clears session storage & cookies from .browser_profile."""
    with sync_playwright() as p:
        try:
            ctx = get_browser_context(p, headless=True)
            ctx.clear_cookies()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=10000)
            page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e){} }")
            ctx.close()
            print("[OK] Session ended and profile cleared.")
            return True
        except Exception as e:
            print(f"[WARN] Error ending session: {e}")
            return False


def wait_for_manual_login(page: Page, timeout_seconds: int = 300) -> bool:
    """
    Directs the user to log in manually if not already authenticated.
    Polls until the dashboard or authenticated indicator is detected.
    """
    page.goto(DASHBOARD_URL)
    page.bring_to_front()

    print("\n" + "=" * 60)
    print("[AUTH] HPC PORTAL AUTHENTICATION")
    print("=" * 60)
    print("Please log in with your credentials in the opened browser window.")
    print("Do NOT share OTP or passwords in code or chat.")
    print("Waiting for dashboard to load...\n")

    start_time = time.time()
    time.sleep(1.5)  # allow initial client-side redirect
    while time.time() - start_time < timeout_seconds:
        current_url = page.url
        if ("/hpc-dashboard" in current_url or "/hpc/" in current_url or "/profile" in current_url) and not (current_url.endswith("/en") or current_url.endswith("/en/")):
            try:
                session_data = page.evaluate('''async () => {
                    try {
                        const res = await fetch('/api/auth/session');
                        return await res.json();
                    } catch(e) {
                        return null;
                    }
                }''')
                if session_data and session_data.get("user"):
                    print("[OK] Authentication confirmed! Proceeding to automation.\n")
                    return True
            except Exception:
                pass
        time.sleep(2)

    raise TimeoutError("Login timed out after 5 minutes. Please try again.")
