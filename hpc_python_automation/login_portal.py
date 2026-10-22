"""
CLI Login Helper:
Opens the official PARAKH HPC portal in a visible browser window,
cleans any stale locks, and waits for manual credentials/OTP entry.
Saves session cookies to .browser_profile.
"""
import sys
from pathlib import Path

# Ensure utf-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from portal.login import start_interactive_session, check_session_status, cleanup_zombie_browsers

def main():
    print("=" * 65)
    print("🎓 PARAKH HPC PORTAL - INTERACTIVE LOGIN")
    print("=" * 65)
    print("Cleaning any stale browser locks...")
    cleanup_zombie_browsers()
    
    print("Launching Chromium browser window directed to:")
    print("🔗 https://hpc.parakh.ncert.gov.in/en")
    print("\nPlease enter your Mobile / Username, Password, and OTP in the browser.")
    print("Waiting for you to reach the dashboard (timeout: 5 minutes)...")
    print("-" * 65)
    
    res = start_interactive_session(timeout_seconds=300)
    if res.get("success"):
        print("\n" + "=" * 65)
        print("🎉 LOGIN SUCCESSFUL!")
        print(f"👤 Teacher: {res.get('user')}")
        if res.get('school'):
            print(f"🏫 School:  {res.get('school')}")
        print(f"🏷️ Role:    {res.get('role')}")
        print("=" * 65)
        print("\n[OK] Session saved! You can now return to http://localhost:8501")
        print("and click 'Connect & Fetch Students from Portal'.")
    else:
        print(f"\n[FAIL] {res.get('error', 'Login timed out or window was closed.')}")

if __name__ == "__main__":
    main()
