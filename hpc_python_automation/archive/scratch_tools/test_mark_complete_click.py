import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_mark_complete_click():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/hpc-credit"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # Check declaration checkbox if not checked
        cb = page.locator("input[type=checkbox]").last
        if not cb.is_checked():
            page.evaluate("(el) => el.click()", cb)
            time.sleep(1)

        # Listen to dialogs or network requests
        page.on("dialog", lambda dialog: print("Dialog opened:", dialog.message, dialog.accept()))
        page.on("response", lambda r: print("API Response:", r.status, r.url) if "hpc" in r.url or "status" in r.url else None)

        mark_btn = page.locator("button:has-text('Mark as Complete')").first
        print("Clicking Mark as Complete...")
        mark_btn.click()
        time.sleep(3)

        # Check for modals
        modals = page.locator(".modal, [role=dialog], div[class*='modal'], div[class*='dialog']").all()
        print(f"Modals found: {len(modals)}")
        for m in modals:
            if m.is_visible():
                print("Visible Modal:", m.inner_text().replace('\n', ' | '))
                # Click Confirm / Yes
                btn = m.locator("button").all()
                for b in btn:
                    print("  Modal button:", b.inner_text().strip())
                    if any(w in b.inner_text().lower() for w in ("yes", "confirm", "complete", "ok")):
                        b.click()
                        time.sleep(2)

        page.screenshot(path='audit_evidence/middle_after_mark_complete_click.png')

        # Go to roster to check
        print("\nChecking roster...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(3)
        rows = page.locator("table tbody tr").all()
        for r in rows:
            t = r.inner_text().strip().replace('\n', ' | ')
            if 'ARBAZ' in t.upper():
                print(f">>> LIVE STATUS: {t} <<<")

        ctx.close()

if __name__ == '__main__':
    test_mark_complete_click()
