import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_open():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Navigating to Middle Stage roster...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(3)

        # Let's inspect Row 0: ARBAZ IQBAL
        row0 = page.locator("table tbody tr").first
        last_cell = row0.locator("td").last
        action_trigger = last_cell.locator(".custom-dropdown-header, label:has-text('⋮'), svg").first
        action_trigger.click()
        time.sleep(1)

        print("[2] Clicking 'Open' in action menu...")
        open_opt = page.locator(".custom-dropdown-item:has-text('Open'), li:has-text('Open'), div:has-text('Open')").last
        open_opt.click()
        time.sleep(4)

        print("Current URL after Open:", page.url)
        page.screenshot(path='audit_evidence/middle_student_page.png')

        # Check navigation tabs / steps
        tabs = page.locator("a, button, [role=tab], .tab, nav *").all()
        tab_texts = set()
        for t in tabs:
            txt = t.inner_text().strip()
            if txt and len(txt) < 30 and any(w in txt.lower() for w in ("part", "credit", "stage", "general", "activity", "interest", "feedback")):
                tab_texts.add(txt)
        print("Detected Form Tabs/Steps:", tab_texts)

        # Check inputs on this page
        inputs = page.locator("input, select, textarea").all()
        print(f"Total form inputs on current page: {len(inputs)}")

        ctx.close()

if __name__ == '__main__':
    test_open()
