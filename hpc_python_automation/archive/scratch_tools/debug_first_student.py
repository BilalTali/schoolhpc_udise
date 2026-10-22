"""
DEBUG SCRIPT: Step-by-step inspection of FIRST student form on PARAKH HPC portal.
Run this directly (not via Streamlit) to see exactly what the automation encounters.

Usage:
    .venv\Scripts\python.exe debug_first_student.py
"""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / ".browser_profile"
EVIDENCE_DIR = ROOT / "audit_evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

STAGE_SLUG = "preparatory-stage"
BASE_URL = "https://hpc.parakh.ncert.gov.in"


def ss(page, label: str):
    fname = EVIDENCE_DIR / f"debug_{label}.png"
    page.screenshot(path=str(fname), full_page=True)
    print(f"\n  [Screenshot saved: debug_{label}.png]")


def print_buttons(page):
    buttons = page.query_selector_all("button")
    print(f"  Visible buttons ({len(buttons)}):")
    for b in buttons[:20]:
        try:
            txt = (b.inner_text() or "").strip()
            vis = b.is_visible()
            dis = b.is_disabled()
            if txt:
                print(f"    - [{txt}] visible={vis} disabled={dis}")
        except Exception:
            pass


def print_url(page):
    print(f"  Current URL: {page.url}")


def get_student_key_from_roster(page):
    roster_url = f"{BASE_URL}/en/hpc/{STAGE_SLUG}"
    print(f"\n[->] Navigating to roster: {roster_url}")
    page.goto(roster_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)
    ss(page, "01_roster")
    print_url(page)

    rows = page.query_selector_all("table tbody tr")
    print(f"  Found {len(rows)} rows in roster table")

    if not rows:
        rows = page.query_selector_all("tr")
        print(f"  Fallback: found {len(rows)} total <tr> elements")
        title = page.title()
        print(f"  Page title: {title}")
        body_text = page.inner_text("body")[:800]
        print(f"  Page body:\n{body_text}")
        return None, None

    first_row = rows[0]
    cells = first_row.query_selector_all("td")
    row_key = first_row.get_attribute("data-tv-row-key") or ""
    student_name = cells[2].inner_text().strip() if len(cells) > 2 else "Unknown"
    adm_num = cells[1].inner_text().strip() if len(cells) > 1 else ""

    print(f"  First student: Name='{student_name}', Adm='{adm_num}', row_key='{row_key}'")
    return row_key, student_name


def inspect_page(page, label):
    ss(page, label)
    print_url(page)
    print("\n  [BUTTONS]")
    print_buttons(page)

    inputs = page.query_selector_all("input:not([type=hidden])")
    print(f"\n  Input fields: {len(inputs)}")
    for i in inputs[:15]:
        t = i.get_attribute("type") or "text"
        n = i.get_attribute("name") or i.get_attribute("placeholder") or i.get_attribute("id") or ""
        ro = "readonly" if i.get_attribute("readonly") is not None else ""
        dis = "disabled" if i.get_attribute("disabled") is not None else ""
        print(f"    input[{t}] n='{n}' {ro} {dis}")

    tables = page.query_selector_all("table")
    print(f"\n  Tables: {len(tables)}")
    for t in tables[:2]:
        rows = t.query_selector_all("tr")
        print(f"    table rows: {len(rows)}")
        for r in rows[:4]:
            cells = r.query_selector_all("th, td")
            cell_texts = [c.inner_text()[:25].strip() for c in cells[:6]]
            print(f"      {cell_texts}")

    errors = page.query_selector_all(".error, [class*='error'], .alert-danger, [class*='alert']")
    if errors:
        print(f"\n  Errors/Alerts: {len(errors)}")
        for e in errors[:3]:
            print(f"    {(e.inner_text() or '')[:120].strip()}")

    modals = page.query_selector_all(".modal-content, [role=dialog]")
    if modals:
        print(f"\n  Modals: {len(modals)}")
        for m in modals[:2]:
            print(f"    {(m.inner_text() or '')[:150].strip()}")


def main():
    print("=" * 60)
    print("PARAKH HPC - First Student Debug Script")
    print("=" * 60)

    with sync_playwright() as p:
        # Kill any leftover lock files first
        for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lf = PROFILE_DIR / lock
            if lf.exists():
                lf.unlink()

        try:
            ctx = p.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=False,
                no_viewport=True,
                args=["--start-maximized"],
            )
        except Exception as e:
            print(f"[ERROR] Could not launch browser: {e}")
            return

        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Check login
        print("\n[->] Checking dashboard...")
        page.goto("https://hpc.parakh.ncert.gov.in/en/hpc-dashboard", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        print_url(page)
        ss(page, "00_dashboard")

        if "/en" in page.url and "hpc-dashboard" not in page.url:
            print("\n*** NOT LOGGED IN. Log in manually. Waiting 90s... ***")
            time.sleep(90)

        # Get first student row key from roster
        row_key, student_name = get_student_key_from_roster(page)

        if not row_key:
            print("\n[FAIL] Could not get row_key. Staying open for 30s.")
            time.sleep(30)
            ctx.close()
            return

        # Navigate to Part-A1
        import base64
        # Try raw key first
        student_url = f"{BASE_URL}/en/hpc/{STAGE_SLUG}/{row_key}/part-A1"
        print(f"\n[->] Navigating to Part-A1 (raw key): {student_url}")
        page.goto(student_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

        if "part-A1" not in page.url and "hpc" not in page.url.split(BASE_URL)[-1]:
            # Try base64
            b64_key = base64.b64encode(row_key.encode()).decode()
            student_url_b64 = f"{BASE_URL}/en/hpc/{STAGE_SLUG}/{b64_key}/part-A1"
            print(f"[->] Trying base64 URL: {student_url_b64}")
            page.goto(student_url_b64, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

        print("\n=== PART-A1 PAGE ===")
        inspect_page(page, "02_partA1")

        # Try clicking Continue
        print("\n[->] Clicking Continue/Save...")
        buttons = page.query_selector_all("button")
        for b in buttons:
            txt = (b.inner_text() or "").strip().lower()
            if any(w in txt for w in ("continue", "next", "save as draft", "save")):
                try:
                    vis = b.is_visible()
                    dis = b.is_disabled()
                    print(f"  Found '{txt}' visible={vis} disabled={dis}")
                    if vis and not dis:
                        b.click()
                        time.sleep(3)
                        print(f"  Clicked '{txt}'")
                        break
                except Exception as ex:
                    print(f"  Error clicking: {ex}")

        print("\n=== AFTER FIRST CONTINUE ===")
        inspect_page(page, "03_after_continue1")

        # Try next Continue
        buttons2 = page.query_selector_all("button")
        for b in buttons2:
            txt = (b.inner_text() or "").strip().lower()
            if "continue" in txt or "next" in txt:
                try:
                    if b.is_visible() and not b.is_disabled():
                        b.click()
                        time.sleep(3)
                        print(f"  Clicked second '{txt}'")
                        break
                except Exception:
                    pass

        print("\n=== AFTER SECOND CONTINUE (Part-A2?) ===")
        inspect_page(page, "04_partA2")

        print("\n[DONE] Staying open 60s for manual inspection...")
        time.sleep(60)
        ctx.close()


if __name__ == "__main__":
    main()
