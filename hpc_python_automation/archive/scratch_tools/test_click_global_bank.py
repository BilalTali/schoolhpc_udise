import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def click_global_bank_btn():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Activity Bank...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
        time.sleep(2)

        # Find the two orange buttons next to "My Activity Bank"
        top_btns = page.locator(".content-header button, div.d-flex button, div:has-text('My Activity Bank') button").all()
        print(f"Top buttons: {len(top_btns)}")
        for idx, b in enumerate(top_btns):
            print(f"  btn[{idx}]: {b.inner_html()}")

        # Click the second button
        if len(top_btns) >= 2:
            print("Clicking 2nd top button (Global Activity Bank)...")
            top_btns[1].click()
            time.sleep(3)
            page.screenshot(path='audit_evidence/clicked_global_bank_btn.png')

            # Select Middle Stage in the modal or page
            rows = page.locator("table tbody tr, .modal table tbody tr").all()
            print(f"Rows found: {len(rows)}")
            for idx, r in enumerate(rows[:10]):
                print(f"  r[{idx}]: {r.inner_text().strip().replace(chr(10), ' | ')}")

        ctx.close()

if __name__ == '__main__':
    click_global_bank_btn()
